"""Public media is a three-object allowlist, separate from private productions."""
import base64,copy,hashlib,io,json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from fastapi.testclient import TestClient
from cloud.api import create_app
from cloud.domain import Problem
from cloud.services import Artifacts,SHOWCASE_FILES,showcase_key
from cloud.infra import deploy

class ShowcaseStore:
    def __init__(self):self.reads=[];self.opens=0
    def describe_showcase(self,name):
        self.reads.append(showcase_key(name));outer=self
        class Blob:
            def open(self,*args,**kwargs):outer.opens+=1;return io.BytesIO(b'0123456789')
        return Blob(),{'size':10,'content_type':'video/mp4'}

class ShowcaseTests(unittest.TestCase):
    def setUp(self):
        self.store=ShowcaseStore()
        self.client=TestClient(create_app(deps=lambda:(None,None,self.store)))
    def test_public_get_head_and_query_cannot_select_a_private_object(self):
        for name in SHOWCASE_FILES:
            response=self.client.get('/api/v1/showcase/'+name+'?object=users/private/movie.mp4')
            self.assertEqual((response.status_code,response.content),(200,b'0123456789'))
            self.assertEqual(response.headers['cache-control'],'public, max-age=3600')
            self.assertEqual(response.headers['content-type'],'video/mp4')
            self.assertEqual(response.headers['content-disposition'],'inline; filename="'+name+'"')
            self.assertEqual(response.headers['content-length'],'10')
            self.assertEqual(response.headers['accept-ranges'],'bytes')
        opens=self.store.opens
        head=self.client.head('/api/v1/showcase/original.mp4')
        self.assertEqual((head.status_code,head.content),(200,b''))
        self.assertEqual(head.headers['content-length'],'10')
        self.assertEqual(self.store.opens,opens)
        self.assertTrue(all(key.startswith('showcase/') for key in self.store.reads))
    def test_ranges_are_bounded_and_malformed_ranges_fail(self):
        path='/api/v1/showcase/original.mp4'
        for value,body,span in [('bytes=2-5',b'2345','2-5'),('bytes=8-',b'89','8-9'),('bytes=-3',b'789','7-9'),('bytes=8-999',b'89','8-9')]:
            response=self.client.get(path,headers={'Range':value})
            self.assertEqual((response.status_code,response.content),(206,body))
            self.assertEqual(response.headers['content-range'],'bytes '+span+'/10')
            self.assertEqual(int(response.headers['content-length']),len(body))
        for value in ('bytes=100-','bytes=5-2','bytes=-0','bytes=-','bytes=0-1,3-4','nonsense','bytes='+'9'*5000+'-'):
            response=self.client.get(path,headers={'Range':value})
            self.assertEqual(response.status_code,416)
            self.assertEqual(response.headers['content-range'],'bytes */10')
            self.assertEqual(response.headers['cache-control'],'no-store')
        head=self.client.head(path,headers={'Range':'bytes=2-5'})
        self.assertEqual((head.status_code,head.content),(206,b''))
        self.assertEqual(head.headers['content-length'],'4')
    def test_unknown_names_traversal_and_private_artifacts_remain_rejected(self):
        for name in ('secret.mp4','ORIGINAL.MP4','users%2Fsecret.mp4','%2e%2e%2Fusers%2Fsecret.mp4','%252e%252e','original.mp4%00'):
            self.assertEqual(self.client.get('/api/v1/showcase/'+name).status_code,404)
        self.assertFalse(self.store.reads)
        for suffix in ('','/artifacts/movie/content'):
            response=self.client.get('/v1/projects/'+'a'*32+suffix)
            self.assertEqual(response.status_code,401)
            self.assertEqual(response.headers['cache-control'],'no-store')
        self.assertEqual(self.client.post('/api/v1/showcase/original.mp4').status_code,405)
    def test_storage_lookup_is_literal_and_rejects_before_bucket_access(self):
        keys=[]
        class Blob:
            size=12
            def reload(self):pass
        class Bucket:
            def blob(self,key):keys.append(key);return Blob()
        with patch.dict('os.environ',{'RENDER_BUCKET':'test-private-bucket'}):
            store=Artifacts(client=SimpleNamespace(bucket=lambda name:Bucket()))
        for name in SHOWCASE_FILES:store.describe_showcase(name)
        self.assertEqual(set(keys),{'showcase/'+name for name in SHOWCASE_FILES})
        for name in ('users/private/movie.mp4','../original.mp4','showcase/original.mp4'):
            with self.assertRaises(Problem):store.describe_showcase(name)
        self.assertEqual(len(keys),3)

class ShowcaseDeploymentTests(unittest.TestCase):
    def setUp(self):
        self.settings={'project':'runtime','bucket':'private-bucket','apiUrl':'https://api.example.invalid',
          'showcaseUploaded':{name:{'object':'showcase/'+name,'verified':True} for name in SHOWCASE_FILES}}
    def test_staging_replaces_only_three_media_assets_and_preserves_local_source(self):
        html=''.join('<source src="'+asset+'">' for asset in deploy.SHOWCASE_SOURCES.values())+'<img src="/assets/poster.jpg">'
        staged,redirects,origin=deploy.stage_showcase(html,self.settings)
        self.assertEqual(origin,'https://api.example.invalid')
        self.assertEqual(len(redirects),3)
        for name,asset in deploy.SHOWCASE_SOURCES.items():
            self.assertIn(origin+'/api/v1/showcase/'+name,staged)
            self.assertIn(asset,html)
        self.assertIn('/assets/poster.jpg',staged)
        self.assertEqual(deploy.stage_showcase(html,{}),(html,[],None))
        bad=copy.deepcopy(self.settings);bad['showcaseUploaded']['original.mp4']['object']='users/private/movie.mp4'
        with self.assertRaises(ValueError):deploy.stage_showcase(html,bad)
        bad=copy.deepcopy(self.settings);bad['apiUrl']='http://api.example.invalid'
        with self.assertRaises(ValueError):deploy.stage_showcase(html,bad)
    def test_operator_upload_checks_all_inputs_and_remote_checksum(self):
        calls=[];body=b'\x00\x00\x00\x18ftypisom'+b'film fixture'
        md5=base64.b64encode(hashlib.md5(body,usedforsecurity=False).digest()).decode()
        class Rest:
            wrong_checksum=False
            def __init__(self,*args):pass
            def request(self,method,url,**kwargs):
                from urllib.parse import parse_qs,urlsplit
                key=parse_qs(urlsplit(url).query)['name'][0];calls.append(key)
                return {'name':key,'size':str(len(body)),'md5Hash':'bad' if self.wrong_checksum else md5,'generation':'1'}
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'cloud').mkdir();paths={}
            for name in SHOWCASE_FILES:
                path=root/name;path.write_bytes(body);paths[name]=path
            settings={'project':'runtime','bucket':'private-bucket'}
            with patch.object(deploy,'GoogleRest',Rest),patch.object(deploy,'ROOT',root):
                deploy.upload_showcase(settings,paths)
                self.assertEqual(set(calls),{'showcase/'+name for name in SHOWCASE_FILES})
                self.assertTrue(all(v['verified'] for v in settings['showcaseUploaded'].values()))
                self.assertTrue((root/'cloud/showcase-upload.json').is_file())
                Rest.wrong_checksum=True
                with self.assertRaisesRegex(RuntimeError,'checksum'):deploy.upload_showcase({'project':'runtime','bucket':'private-bucket'},paths)
                calls.clear();paths['original.mp4']=root/'missing.mp4'
                with self.assertRaises(ValueError):deploy.upload_showcase(settings,paths)
                self.assertFalse(calls)
