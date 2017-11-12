from taxonomy import models as taxonomy_models
from postgres_copy import CopyMapping
from django.core.management.base import BaseCommand

class Command(BaseCommand):

    def handle(self, *args, **kwargs):
        self.csv_to_db()

    def get_raw_file(self, name):

        ua_dict = {
                'user_agent': 'user_agent'
        }

       
        taxonomy_dict = {
            'level_0': 'level_0',
            'level_1': 'level_1',
        }

        taxonomy_path = 'taxonomy/raw_files/custom_taxonomy.csv'
        taxnomy_model = taxonomy_models.RawTaxonomy,
       
        kwargs = {
                'taxonomy': {
                    'raw': taxonomy_dict,
                    'path': taxonomy_path,
                    'model': taxnomy_model,       
                },
            }
        return kwargs[name]

    def csv_to_db(self):
        raw_contents = self.get_raw_file('taxonomy')
        model = raw_contents.get('model')[0] # somehow we're getting a tuple
        path = raw_contents.get('path')
        raw_dict = raw_contents.get('raw')
        obj = CopyMapping(model, path, raw_dict)
        msg = 'CopyMapping incomplete: uncomment save() to make db changes'
        print msg
        # obj.save()