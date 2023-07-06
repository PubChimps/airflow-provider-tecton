# Copyright 2022 Tecton, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import datetime
import logging
import pandas
import pprint
import time
from typing import Any
from typing import Callable
from typing import Sequence
from typing import Union

from airflow.models import BaseOperator

from airflow_tecton.hooks.tecton_hook import TectonHook
from airflow_tecton.operators.df_utils import upload_df_pandas


class TectonJobOperator(BaseOperator):
    """
    An Airflow operator that launches a Tecton job, and waits for its completion. If the latest job with the same params
    is running, it will cancel it first. If the latest job with the same params is successful, this will return without
    running a new job.

    Use this if you want to submit a Tecton job via Airflow and control retries via Airflow. Each attempt of this operator creates 1 job.
    """

    template_fields: Sequence[str] = ("start_time", "end_time")

    def __init__(
        self,
        *,
        conn_id: str = "tecton_default",
        workspace: str,
        feature_view: str,
        online: bool,
        offline: bool,
        start_time: Union[str, datetime.datetime] = "{{ data_interval_start }}",
        end_time: Union[str, datetime.datetime] = "{{ data_interval_end }}",
        allow_overwrite: bool = False,
        df_generator: Callable = None,
        **kwargs,
    ):
        """

        :param conn_id: Airflow connection ID for Tecton connection
        :param workspace: Workspace of FeatureView
        :param feature_view: FeatureView name
        :param start_time: Start of time range for materialization job
        :param end_time: End of time range for materialization job
        :param online: Whether job writes to online store
        :param offline: Whether job writes to offline store
        :param allow_overwrite: Whether jobs are able to run materialization for periods that previously have materialized data. Note that this can cause inconsistencies if the underlying data has changed.
        :param kwargs: Airflow base kwargs passed to BaseOperator
        """
        super().__init__(**kwargs)
        self.workspace = workspace
        self.feature_view = feature_view
        self.online = online
        self.offline = offline
        self.start_time = start_time
        self.end_time = end_time
        self.allow_overwrite = allow_overwrite
        self.conn_id = conn_id
        self.job_id = None
        self.df_generator = df_generator

    def execute(self, context) -> Any:
        hook = TectonHook.create(self.conn_id)

        job = hook.find_materialization_job(
            workspace=self.workspace,
            feature_view=self.feature_view,
            online=self.online,
            offline=self.offline,
            start_time=self.start_time,
            end_time=self.end_time,
            job_type="ingest" if self.df_generator else "batch",
        )
        if job:
            logging.info(f"Existing job found: {pprint.pformat(job)}")
            if job["state"].lower().endswith("running"):
                logging.info("Job in running state; cancelling")
                hook.cancel_materialization_job(
                    workspace=self.workspace,
                    feature_view=self.feature_view,
                    job_id=job["id"],
                )
                while (
                    not hook.get_materialization_job(
                        workspace=self.workspace,
                        feature_view=self.feature_view,
                        job_id=job["id"],
                    )["job"]["state"]
                    .lower()
                    .endswith("manually_cancelled")
                ):
                    logging.info(f"waiting for job to enter state manually_cancelled")
                    time.sleep(60)
            elif job["state"].lower().endswith("success"):
                if self.allow_overwrite:
                    logging.info(
                        "Overwriting existing job in success state; (allow_overwrite=True)"
                    )
                else:
                    logging.info("Existing job in success state; exiting")
                    return

        if self.df_generator:
            resp = self.ingest_feature_table_with_pandas_df(hook)
        else:
            resp = hook.submit_materialization_job(
                workspace=self.workspace,
                feature_view=self.feature_view,
                online=self.online,
                offline=self.offline,
                start_time=self.start_time,
                end_time=self.end_time,
                allow_overwrite=self.allow_overwrite,
                tecton_managed_retries=False,
            )
        self.job_id = resp["job"]["id"]
        job_result = hook.get_materialization_job(
            self.workspace, self.feature_view, self.job_id
        )["job"]
        while job_result["state"].upper().endswith("RUNNING"):
            if "attempts" in job_result:
                attempts = job_result["attempts"]
                latest_attempt = attempts[-1]
                logging.info(
                    f"Latest attempt #{len(attempts)} in state {latest_attempt['state']} with URL {latest_attempt['run_url']}"
                )
            else:
                logging.info(f"No attempt launched yet")
            time.sleep(60)
            job_result = hook.get_materialization_job(
                self.workspace, self.feature_view, self.job_id
            )["job"]
        if job_result["state"].upper().endswith("SUCCESS"):
            return
        else:
            raise Exception(
                f"Final job state was {job_result['state']}. Final response:\n {job_result}"
            )

    def ingest_feature_table_with_pandas_df(self, hook):
        df_info = hook.get_dataframe_info(self.feature_view, self.workspace)

        df_path = df_info["df_path"]
        upload_url = df_info["signed_url_for_df_upload"]

        df = self.df_generator()
        upload_df_pandas(upload_url, df)

        return hook.ingest_dataframe(self.feature_view, df_path, self.workspace)

    def on_kill(self) -> None:
        if self.job_id:
            logging.info(f"Attempting to kill job {self.job_id}")
            hook = TectonHook.create(self.conn_id)
            hook.cancel_materialization_job(
                self.workspace, self.feature_view, self.job_id
            )
            logging.info(f"Successfully killed job {self.job_id}")
        else:
            logging.debug(f"No job started; none to kill")
