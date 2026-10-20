"""Cloud Run dispatch and owner-scoped artifact storage."""
import os
from datetime import timedelta
from google.cloud import run_v2, storage
from .domain import ARTIFACT_FILES, MIME_TYPES, Problem, storage_prefix

class Launcher:
    def __init__(self, client=None, executions=None):
        self.client=client or run_v2.JobsClient()
        self.executions=executions or run_v2.ExecutionsClient()
        project=os.environ['GOOGLE_CLOUD_PROJECT'];region=os.getenv('RUN_REGION','us-central1');job=os.getenv('RENDER_JOB','second-nature-render')
        self.name=job if job.startswith('projects/') else f'projects/{project}/locations/{region}/jobs/{job}'
    def start(self,jid):
        request=run_v2.RunJobRequest(name=self.name,overrides=run_v2.RunJobRequest.Overrides(
            task_count=1,timeout=timedelta(seconds=int(os.getenv('JOB_TIMEOUT_SECONDS','7200'))),
            container_overrides=[run_v2.RunJobRequest.Overrides.ContainerOverride(env=[run_v2.EnvVar(name='JOB_ID',value=jid)])]))
        operation=self.client.run_job(request=request,timeout=30)
        return operation.operation.name
    def cancel(self,execution):
        if execution:self.executions.cancel_execution(request=run_v2.CancelExecutionRequest(name=execution),timeout=15)
    def status(self,execution):
        record=self.executions.get_execution(request=run_v2.GetExecutionRequest(name=execution),timeout=15)
        return {'finished':bool(record.completion_time),'cancelled':record.cancelled_count>0,'failed':record.failed_count>0}

class Artifacts:
    def __init__(self,client=None):
        self.client=client or storage.Client(project=os.environ['GOOGLE_CLOUD_PROJECT'])
        self.bucket=self.client.bucket(os.environ['RENDER_BUCKET'])
    def blob(self,uid,pid,kind):
        if kind not in ARTIFACT_FILES:raise Problem(404,'Artifact not found.')
        return self.bucket.blob(storage_prefix(uid,pid)+ARTIFACT_FILES[kind])
    def describe(self,uid,pid,kind):
        blob=self.blob(uid,pid,kind)
        try:blob.reload()
        except Exception as exc:
            from google.api_core.exceptions import NotFound
            if isinstance(exc,NotFound):raise Problem(404,'This artifact is unavailable. It may not have been produced yet, or its seven-day storage period may have ended.') from exc
            raise
        return blob,{'size':blob.size,'content_type':MIME_TYPES[kind],'updated_at':blob.updated.isoformat() if blob.updated else None}
