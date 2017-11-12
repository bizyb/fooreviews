from django.db import connection
import services.loggers as loggers
logger = loggers.Loggers(__name__).get_logger()

class MirateTable(object):
    '''
    Migrates db table entries internally; useful when adding, removing,
    or decoupling apps. 

    NB: Serialization and de-serialization doesn't work for this sort of 
        process. 
    '''

    def __init__(self, *args, **kwargs):
        self.tables = self._get_tables()

    def _get_tables(self):
        '''
        Return source and destination tables. 

        NB: Must edit hard-coded table names if reusing the module.
        '''
        tables = [
                    # {
                    #     'old': 'crawler_selector',
                    #     'new': 'parsers_selector',
                    # },
                    # {
                    #     'old': 'crawler_reviewraw',
                    #     'new': 'parsers_reviewraw',
                    # },
                    
        ]
        return tables

    def migrate(self):
        for table in self.tables:
            old = table.get('old')
            new = table.get('new')
            query = "INSERT INTO {} SELECT * FROM {}".format(new, old)
            logger.info('Executing query={}'.format(query))
            cursor = connection.cursor()
            cursor.execute(query)
