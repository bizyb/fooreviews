import os
from services import db_dump_path
CURR_PATH = os.path.dirname(os.path.realpath(__file__))
LOCAL_PATH = db_dump_path.get_local_path(CURR_PATH)

from django.core.management.base import BaseCommand
from data_transfer import data_transfer
import data_transfer.__base_db_transfer as dbt
import services.loggers as loggers
logger = loggers.Loggers(__name__).get_logger()

class Command(BaseCommand, dbt.BaseDBTransfer):
    # TODO: Set an environment variable for staging and production
    # allow this command to run only if in staging; disallow from
    # the production server
    def __init__(self, *args, **kwargs):
        super(Command, self).__init__(*args, **kwargs)

    def handle(self, *args, **kwargs):
        self._load_data()

    def _count_objects(self):
        '''
        Output the final count of db entries for easy verification.
        '''
        count_list = []
        models = self.get_fr_models()
        for table, m in models.items():
            count_list.append((table, m.objects.all().count()))
        count_sorted = sorted(count_list)
        logger.info('\nFinal Count of Database Entries')
        for count_tup in count_sorted:
            logger.info(count_tup)
        logger.info('\n')

    def _load_data(self):
        models = self.get_fr_models()
        for name, model in models.items():
            dt = data_transfer.DataTransfer(name, model, logger=logger,
                 fr_data=True, path_dump=LOCAL_PATH)
            dt.stage_loading()
        self._count_objects()


