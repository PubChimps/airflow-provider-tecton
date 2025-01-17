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
import textwrap
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator

from tecton_provider.sensors.tecton_sensor import TectonSensor

WORKSPACE = "my_workspace"
FEATURE_SERVICE = "my_feature_service"

with DAG(
    dag_id="example_tecton_sensor",
    description=textwrap.dedent(
        """
        This example shows a FeatureService with both online and offline materialization.

        This example can be adapted to work with Triggered and Scheduled FeatureViews as well,
        a FeatureService which can have a mix of both.
       
        Model training starts when the offline feature store is ready,
        and a report when the online feature store is up to date. 

        We use example BashOperators in place of actual training/reporting operators.
    """
    ),
    start_date=datetime(2022, 7, 14),
    schedule_interval=timedelta(days=1),
) as dag:
    wait_for_feature_service_online = TectonSensor(
        task_id="wait_for_fs_online",
        workspace=WORKSPACE,
        feature_service=FEATURE_SERVICE,
        online=True,
        offline=False,
    )
    wait_for_feature_service_offline = TectonSensor(
        task_id="wait_for_fs_offline",
        workspace=WORKSPACE,
        feature_service=FEATURE_SERVICE,
        online=False,
        offline=True,
    )
    train_model = BashOperator(
        task_id="train_model", bash_command='echo "model trained!"'
    )
    report_online_done = BashOperator(
        task_id="report_online_done", bash_command='echo "online data ready!"'
    )
    wait_for_feature_service_online >> report_online_done
    wait_for_feature_service_offline >> train_model
