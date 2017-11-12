from django.core.management.base import BaseCommand
import fooreviews.article_data.publisher as publisher
import services.loggers as loggers
logger = loggers.Loggers(__name__).get_logger()

class Command(BaseCommand): 
    
    def add_arguments(self, parser):
        help = "Publish article for a given FRSKU or a list of FRSKUs "    
        arguments = [
                {
                    'argument': '--frsku',
                    'settings': {
                        'nargs': '+',
                        'type': str,
                        'help': help,
                    }
                },       
        ]

        for arg_dict in arguments:
            arg = arg_dict.get('argument')
            settings = arg_dict.get('settings')
            parser.add_argument(arg, **settings)

    def handle(self, *args, **kwargs):
        self.frsku_list = kwargs.get('frsku')
        if self.frsku_list:
            for frsku in self.frsku_list:
                self._run_publisher(frsku)
        else:
            msg = 'FRSKU not given. Please try again.\n'
            logger.info(msg)


    def _run_publisher(self, frsku):
        try:
            msg = 'Preparing to publish an article for FRSKU={}'
            msg = msg.format(frsku)
            logger.info(msg)
            pub = publisher.ArticlePublisher(frsku)
            pub.publish()
            msg = 'Published an article for FRSKU={}'
            msg = msg.format(frsku)
            logger.info(msg)
        except Exception as e:
            msg = '{}: {}'.format(type(e).__name__, e.args[0])
            logger.exception(msg)
