
from django.db.models.signals import post_save, pre_delete, pre_save
import os
import services.loggers as loggers
logger = loggers.Loggers(__name__).get_logger()

class ESIndexSignal(object):
	'''
	Updates or deletes objects from elasticsearch index in sync 
	with the Postgres database. For Articles, any change to draft/publish 
	fields automatically updates ES index, effectively adding or 
	removing it from the front-end. We also have a redundancy in views.py, 
	where we raise 404 if status != published.
	'''
	def __init__(self, sender):
		# instatiate the class object with the model sending the signal 
		self.sender = sender
		self.indexing_enabled = True
		self.unpublish = False

	def ready(self):
		post_save.connect(self.update, sender=self.sender)
		pre_delete.connect(self.delete, sender=self.sender)

	def update(self, instance, **kwargs):
		'''
		Update ES search index. If signal object is models.Product,
		retrieve the models.Article object that belongs to it and recusrively
		update the index. 

		NB: index_obj == None when the recursion ends so we don't have to call 
		the non-existent indexing() function on a models.Product instance. 
		'''

		class_name = type(instance).__name__ 
		index_obj, instance = self.get_index_obj(class_name, instance=instance)
		if self.unpublish:
			# unpublish any article whose status=draft
			self.delete(instance)
		if self.indexing_enabled and index_obj and instance: 
			instance.indexing(bulk=False, index=index_obj).save()

	def delete(self, instance, **kwargs):
		'''
		Delete object from ES index.
		'''
		class_name = type(instance).__name__
		index_obj, instance = self.get_index_obj(class_name, instance=instance)
		if index_obj and instance:
			instance.indexing(bulk=False, index=index_obj).delete(ignore=404)


	def get_index_obj(self, name, instance=None):
		from search.index import es_indexer
		index_obj = None
		if name == 'Article':
			index_obj = es_indexer.ArticleIndex
			if instance.draft:
				self.indexing_enabled = False
				self.unpublish = True
			elif instance.published:
				self.indexing_enabled = True
				self.unpublish = False
		elif name == 'Slug':
			index_obj = es_indexer.SlugIndex
		elif name == 'AggregationField':
			index_obj = es_indexer.AggregationFieldIndex
		elif name == 'SortField':
			index_obj = es_indexer.SortFieldIndex
		elif name == 'Product':
			index_obj = es_indexer.ArticleIndex
			instance = self._reverse_instance(instance)
		return index_obj, instance

	def _reverse_instance(self, instance):
		'''
		Do a reverse lookup and get a child object belonging to instance. 

		This sort of lookup only applies when instance=Product. We want to
		get the corresponding Article instance. ES indexing is not enabled 
		on models.Product (models.Article inherits all the necessary fields
		from models.Product for indexing). Thus, when changes are made to 
		the product entry, we want to update the index for the Article 
		object instead. 
		'''
		try:
			article_obj_set = instance.product.all()
			article_obj = article_obj_set.filter(published=True)[0]
			instance = article_obj
		except Exception as e:
			msg = '{}: {}'.format(type(e).__name__, e.args[0])
			logger.exception(msg)
			instance = None
		return instance

class RawSummarySignal(object):
	# TODO: fr_site and fr_data should only have code for the appropriate signals
	'''
	Updates RawSummary table when data regeneration is requested.
	'''
	def __init__(self, sender):
		self.sender = sender

	def ready(self):
		post_save.connect(self.handle_command, sender=self.sender)

	def handle_command(self, instance, **kwargs):
		if instance.generate_data:
			self._generate_data(instance)	
		elif instance.output_summary:
			self._summary_to_file(instance)
	def _generate_data(self, instance):
		import ml.meta.data_generator as dgen
		if instance.generate_data.lower() == 'generate data':
			instance.generate_data = ''
			instance.save()
			d = dgen.MetadataGenerator(frsku=instance.frsku, clear_db=True)
			executor = ThreadPoolExecutor(max_workers=1)
			executor.submit(d.generate_data)
	def _summary_to_file(self, instance):
		if instance.output_summary.lower() == 'output raw summary':
			path = 'file_dump/summary/' + instance.frsku
			filename = path + '/raw_summary.txt'
			try:
				instance.output_summary = ''
				instance.save()
				os.makedirs(path)
			except OSError:
				# make sure we have a directory and not just a file
				if not os.path.isdir(path):
					raise
			try:
				with open(filename, 'w') as f:
					f.write(instance.summary)
			except Exception as e:
				msg = '{}: {}'.format(type(e).__name__, e.args[0])
				logger.exception(msg)
