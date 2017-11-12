
from django.core.management.base import BaseCommand
import fnmatch
import os
import services.loggers as loggers
logger = loggers.Loggers(__name__).get_logger()

class Command(BaseCommand):
    def __init__(self, *args, **kwargs):
        super(Command, self).__init__(*args, **kwargs)

    def handle(self, *args, **kwargs):
        self._purge_log()

    def _purge_log(self):
        log_files = []
        for dirpath, dirnames, files in os.walk('.'):
            for f in fnmatch.filter(files, '*.log'):
                file_name = os.path.join(dirpath, f)
                log_files.append(file_name)
                msg = 'Purged log file {}'.format(file_name)
                logger.info(msg) 
                os.remove(file_name)