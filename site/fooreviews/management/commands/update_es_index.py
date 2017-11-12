from search.index import es_indexer
from django.core.management.base import BaseCommand

class Command(BaseCommand):
    def __init__(self, *args, **kwargs):
        super(Command, self).__init__(*args, **kwargs)

    def handle(self, *args, **kwargs):
        # Update Elasticsearch index for all 
        es_indexer.bulk_index()


