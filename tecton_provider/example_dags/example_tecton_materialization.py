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

from tecton_provider.operators.tecton_materialization_operator import TectonMaterializationOperator
from tecton_provider.sensors.tecton_sensor import TectonSensor

WORKSPACE = "my_workspace"
FEATURE_VIEW = "my_batch_feature_view"

with DAG(
    dag_id="example_tecton_materialization",
    default_args={"retries": 3},
    description=textwrap.dedent(
        """
            This example shows a use case where you have a BatchFeatureView with triggered materialization
            where Tecton handles retries. Note that the retry parameters
            used are standard Airflow retries.

            We use TectonSensor to monitor the offline and online stores.

            Model training when the offline feature store is ready, as well as
            Reporting starts when the online feature store is up to date to our monitoring.

            BashOperators are used in place of actual training/reporting operators.
        """
    ),
    start_date=datetime(2022, 7, 10),
    schedule_interval=timedelta(days=1),
) as dag:
    process_hive_data = BashOperator(
        task_id="process_hive_data", bash_command='echo "hive data processed!"'
    )
    tecton_materialization = TectonMaterializationOperator(
        task_id="materialize_tecton",
        workspace=WORKSPACE,
        feature_view=FEATURE_VIEW,
        online=True,
        offline=True,
    )
    data_ready = TectonSensor(
        task_id="wait_for_data",
        workspace=WORKSPACE,
        feature_view=FEATURE_VIEW,
        online=True,
        offline=True,
    )
    train_model = BashOperator(
        task_id="train_model", bash_command='echo "model trained!"'
    )
    report_online_done = BashOperator(
        task_id="report_online_done", bash_command='echo "online data ready!"'
    )
    process_hive_data >> tecton_materialization >> data_ready >> train_model
    data_ready >> report_online_done
