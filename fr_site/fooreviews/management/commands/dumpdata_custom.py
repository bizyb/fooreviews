import os
from services import db_dump_path #set data_transfer directory
CURR_PATH = os.path.dirname(os.path.realpath(__file__))
LOCAL_PATH = db_dump_path.get_local_path(CURR_PATH)

from django.core.management.base import BaseCommand
import data_transfer.__base_db_transfer as dbt
from data_transfer import data_transfer
import services.loggers as loggers
logger = loggers.Loggers(__name__).get_logger()

class Command(BaseCommand, dbt.BaseDBTransfer):

    def add_arguments(self, parser):
        help = "Indicate data dump type as 'all' or 'frsku'"
        help_frsku = 'Dump data for a given FRSKU to be loaded into fr_site.' 
        help_table = 'Indicate transfer type as staging_to_data, '
        help_table += 'data_to_staging, staging_to_prod or initial'   
        arguments = [
                {
                    'argument': 'dump_type',
                    'settings': {
                        'nargs': '+',
                        'type': str,
                        'help': help,
                    }
                },
                {
                    'argument': '--frsku',
                    'settings': {
                        'nargs': '+',
                        'type': str,
                        'help': help_frsku,
                    }
                },
                {
                    'argument': '--transfer_type',
                    'settings': {
                        'nargs': '+',
                        'type': str,
                        'help': help_table,
                    }
                },        
        ]

        for arg_dict in arguments:
            arg = arg_dict.get('argument')
            settings = arg_dict.get('settings')
            parser.add_argument(arg, **settings)

    def handle(self, *args, **kwargs):
        self.frsku_list = kwargs.get('frsku')
        self.transfer_type = kwargs.get('transfer_type')
        self.frsku = None
        if self.frsku_list:
            self.frsku = self.frsku_list[0]

        if self.transfer_type:
            self.transfer_type = self.transfer_type[0]

        self._dump_data()

    def _dump_data(self):
        models = self.get_fr_models(transfer_type=self.transfer_type)
        for name, model in models.items():
            try:
                logger.info('Requesting data dump for {}'.format(name))
                dt = data_transfer.DataTransfer(name, model, logger=logger,
                                                frsku=self.frsku,
                                                path_dump=LOCAL_PATH)
                SUCCESS = dt.stage_dumping()
                if SUCCESS:
                    msg = 'Successfully dumped data for {}'.format(name)
                else:
                    msg = 'Failed to dump data for {}'.format(name)
                logger.info(msg)
            except Exception as e:
                msg = '{}: {}'.format(type(e).__name__, e.args[0])
                logger.exception(msg)
