import dateutil.parser as date_parser
import glob
import json
import ml.models as m_models
import sql_reset
import os
import shutil
from django.core import serializers
from datetime import datetime
import services.common_helper as ch

class DataTransfer(object):
	'''
	Facilitates selective data dumping and loading in order to allow for 
	a hassle-free data transfer across devevelopment, staging, and 
	production servers as appropriate.

	The rationale behind the need for transferring data back and forth is that
	it forces us to keep our apps and servers separate, i.e. there is no need 
	to have the main site on the same server as the one used for data mining
	and analysis. By keeping them separate, we can pick and choose the 
	server that provides the best set of CPU and RAM specs for the task at 
	hand. 

	No new data ever gets created on the production server. We only push to 
	it from the staging server. All other pulling and pushing events are 
	between the analysis and staging servers.

	NB: This module resides in its own repository. A copy is found on each of
	the servers. Any commits made need to be pushed/pulled as appropriate.

	Some background:
        Webapp was our only django project for the last eight months or so. 
        Since our code base has grown considerably, it became necessary to 
        separate the prject into two: fooreviews_site and fooreviews_data. 
        Fr_site is the main production site that is in sync with the staging 
        server. However, we have no staging for fr_data. Fr_data's primary 
        task is to mine all review data and run the machine learning modules.
        Initially, our data transfer will be from webapp to fr_site and fr_data, 
        the decoupled projects. Thereafter, we'll transfer the local db entries from
		fr_site and fr_data to their cloud servers. In the futuer, data
		transfers between thse two servers will be bi-direcitonal. (Although 
		the service provider already has daily backups for our entire analysis 
		server (weekly backups for staging and production since their content
		is relatively static) we'll use the JSON files we generate for
		making periodic offline backups. 

		NB: We've left out several tables from the data transfer process.
			These would be article or plotting data caches that we generate 
			automatically for performance reasons.
	'''

	def __init__(self, name, model, **kwargs):
		self.name = name
		self.model = model
		self.domain = None
		self.subdomain = None
		self.frsku = kwargs.get('frsku')
		self.destination = kwargs.get('destination')
		self.logger = kwargs.get('logger')
		self.fr_data = kwargs.get('fr_data')
		self.path_dump = kwargs.get('path_dump')
		self.obj_set = self._get_obj_set()

	def _get_obj_set(self):
		'''
		Return db queryset for dumping or loading. If we're working with 
		corpus caches, set the domain and subdomain. This way, we can separate
		the output easily. Because the cache size is in the GB range, we can 
		selectively load only the data that we want.

		NB: Ordering the queryset by primary key allows us to index the
		iteratable objects when dumping data. Otherwise, the whole queryset gets
		loaded to memory, leading to Out of Memory issues and eventually getting
		killed by the OS. We avoid this by taking advantage of Django's lazy 
		querying, where no db query is made until a specific object is requested.
		This is what indexing the iteratable queryset does. 

		We can also index the queryset without sorting it. However, this is shown 
		to be unreliable. Queryset objects can appear multiple times whithin the 
		same indexed iteration, leading to some of the objects not appearing at 
		all. It's not clear why this happens but imposing some ordering seems 
		to return a semi-immutable iteratable (we can't slice it but the order 
		is fixed and the objects are all unique). 
		'''
		if self.frsku:
			# Get data for transferring to fr_site
			if self.name in ['ProductRaw', 'Article']:
				params = {'product__frsku': self.frsku}
			elif self.name in ['Product', 'Data']:
				params = {'frsku': self.frsku}
			elif self.name == 'WhereToBuy':
				params = {'article__product__frsku': self.frsku}
			else:
				params = {}
				if self.name != 'Merchant':
					params = {'frsku': self.frsku}
			obj_set = self.model.objects.filter(**params).order_by('id')
		else:
			obj_set = self.model.objects.all().order_by('id')
			# obj_set = self.model.objects.filter(data_dumped=False).order_by('id')
		if self.name in ['CrawlCache', 'CrawlCorpusCache', 'ReviewRaw']:
			# self._set_domain(obj_set)
			pass
		return obj_set


	def _set_domain(self, obj_set):
		msg = 'Setting domain: object count={}'.format(obj_set.count())
		self.logger.info(msg)
		for index, obj in enumerate(obj_set.iterator()):
			try:
				if not obj.domain:
					msg = 'Setting domain on object index: {}'.format(index)
					self.logger.info(msg)
					if self.name == 'CrawlCorpusCache':
						obj.domain = obj.crawl_corpus_url.corpus_landing_cache.\
									corpus_landing_url.lda_training_domain.domain
						obj.subdomain = obj. crawl_corpus_url.corpus_landing_cache.\
									corpus_landing_url.lda_training_domain.subdomain
					elif self.name == 'CrawlCache':
						obj.domain = obj.crawl_queue.crawl_corpus_parsed.\
									crawl_corpus_cache.crawl_corpus_url.\
									corpus_landing_cache.corpus_landing_url.\
									lda_training_domain.domain
						obj.subdomain = obj.crawl_queue.crawl_corpus_parsed.\
									crawl_corpus_cache.crawl_corpus_url.\
									corpus_landing_cache.corpus_landing_url.\
									lda_training_domain.subdomain
					obj.save()
				else:
					msg = 'Domain already set on object index: {}'.format(index)
					self.logger.info(msg)
			except AttributeError as e:
				msg = '{}: {}'.format(type(e).__name__, e.args[0])
				self.logger.exception(msg)
				pass


	def _serialize(self, obj):
		'''
		Serialize a Django model instance and return a dictionary.
		'''
		serialized = serializers.serialize('json', [obj, ])
		return serialized

	def _deserialize(self, JSON):
		'''
		Deserialize a dictionary of model instances and return a list 
		of DeserializedObject objects.
		'''

		deserialized_list = []
		for index, data in JSON.items():
			des_generator = serializers.json.Deserializer(data)
			des_obj = [obj for obj in des_generator][0]
			deserialized_list.append(des_obj)
		return deserialized_list

	def _save_to_file(self, data, timestamp, offset=0):
		'''
		Save the serialized data to a json file. 
		'''
		root_path = 'file_dump/db_dump/'
		ch.make_directory(self.logger, root_path)
		path = root_path + '{}_{}_{}.json'
		filename = path.format(self.name, timestamp, offset)
		if self.domain and self.subdomain:
			path = 'file_dump/db_dump/{}_{}_{}_{}_{}.json'
			filename = path.format(self.name, self.domain, self.subdomain, 
									timestamp, offset)
		EXISTS =  os.path.isfile(filename)
		if EXISTS:
			with open(filename, 'r') as f:
				feed = json.load(f)
				feed.update(data)
			with open(filename, 'w') as f:
				json.dump(feed, f)
				msg = 'Appended data for {} to {}'
		else:
			with open(filename, 'w') as f:
				json.dump(data, f)
				msg = 'Created new json file for {} with filename={}'
		self.logger.info(msg.format(self.name, filename))


	def _get_batch_size(self):
		'''
		Return a batch size for number of model objects to write to file 
		at a time. We vary the batch size depending on the table and the
		total system RAM. Tables with page caches require more memory 
		and thus smaller batch size. Those with parsed content require 
		less memory so bigger batch size. 
		'''
		from psutil import virtual_memory
		mem = virtual_memory()
		RAM_SIZE = mem.total
		RAM_SIZE = int(RAM_SIZE/1024000000)
		REDUCTION_FACTOR = RAM_SIZE/16 # 16 is just the RAM size of our MacBook
		if self.name in ['CrawlCorpusCache', 'CrawlCache', 'CorpusLandingCache']:
			batch = 15
		else:
			batch = 10000
		batch = batch*REDUCTION_FACTOR
		if batch == 0:
			batch = 1000
		return batch

	def stage_dumping(self):
		'''
		Stage data dumping. Group training data by corpus domain and subdomain.
		'''
		DUMP_COMPLETE = False
		if self.name in ['CrawlCorpusCache', 'CrawlCache', 'ReviewRaw']:
			domain_set = m_models.TrainingDomain.objects.all()
			for dom_obj in domain_set:
				if self.name == 'ReviewRaw':
					params = {
						'crawl_cache__domain': dom_obj.domain, 
						'crawl_cache__subdomain': dom_obj.subdomain, 
					}
				else:
					params = {
							'domain': dom_obj.domain,
							'subdomain': dom_obj.subdomain,
					}
				obj_set = self.obj_set.filter(**params)
				self._set_domain_str(dom_obj)
				DUMP_COMPLETE = self._dump_data(obj_set)
		else:
			DUMP_COMPLETE = self._dump_data(self.obj_set)
		return DUMP_COMPLETE

	def _set_domain_str(self, domain_obj):
		self.domain = domain_obj.domain
		self.subdomain = domain_obj.subdomain
		self.domain = self.domain.replace(' ', '_').replace('&', 'and')
		self.subdomain = self.subdomain.replace(' ', '_').replace('&', 'and')
	
	def _dump_data(self, obj_set):
		'''
		Dump database entries to a JSON file. In order to avoid Out of Memory 
		errors, write to file in bulk as determined by the batch size.
		'''

		JSON = {}
		BATCH_SIZE = self._get_batch_size()
		timestamp = datetime.now().isoformat().replace(':', '_')
		count = obj_set.count()
		if count:
			msg = 'Dumping data for {} count={}'.format(self.name, count)
			self.logger.info(msg)
			for index, obj in enumerate(obj_set.iterator()):
				print 'Index: {}'.format(index)
				try:
					dumpable = self._serialize(obj)
					JSON[index] = dumpable
					if index % BATCH_SIZE == 0:
						if index != 0:
							OFFSET = index - BATCH_SIZE
							self._save_to_file(JSON, timestamp, offset=OFFSET)
							JSON = {}
					if index == count-1:
						OFFSET = index - (index % BATCH_SIZE)
						self._save_to_file(JSON, timestamp, offset=OFFSET)
					obj.data_dumped = True
					obj.save()
				except IndexError as e:
					msg = '{}: {}'.format(type(e).__name__, e.args[0])
					self.logger.exception(msg)
					msg = 'Index={} count={} table={}'
					msg = msg.format(index, count, self.name)
					self.logger.info(msg)
		else:
			if not self.domain:
				self.domain = 'NA'
				self.subdomain = 'NA'
			msg = 'No untransferred db entries found for db TABLE={} DOMAIN={}'
			msg = msg.format(self.name, self.domain)
			msg += ' SUBDOMAIN={}'.format( self.subdomain)
			self.logger.info(msg)
		return True

	def _get_files(self):
		'''
		Return full file paths of all dumped jsons. If regex matching picks up 
		incorrect files, i.e. those whose table name is a substring of another 
		table, drop them from the list.

		Need to disambiguate matches for:
			Product # picks up Product, ProductRaw, and ProductTaxonomy
			ProductRaw # only picks up ProductRaw
			ProductTaxonomy #only picks up ProductTaxonomy
		'''
		ch.make_directory(self.logger, self.path_dump)
		path = self.path_dump + self.name + '*.json'
		all_file_names = [filename for filename in glob.glob(path)]
		if self.name == 'Product':
			all_file_names = [name for name in all_file_names \
								if 'ProductTaxonomy' not in name]
			all_file_names = [name for name in all_file_names if \
									'ProductRaw' not in name]
		
		return all_file_names

	def _object_exists(self, obj_id):
		'''
		Return true if a db record exists for the given row ID and table.  
		'''
		obj_set = self.model.objects.filter(id=obj_id)
		if self.frsku:
			# If frsku is given, wefg're loading data from fr_data to fr_site. 
			# That means we need to clear the db so we can update the old 
			# data and also add new ones.
			obj_set.all().delete()
		EXISTS = obj_set.exists()
		return EXISTS

	def stage_loading(self):
		'''
		Load json objects to db. If db model objects have ForeignKey relation
		within the same table, load the parents first and then the children.
		Otherwise, load the objects in the first iteration (this assumes
		that for objects with ForeignKey relation with other table objects, 
		the table with the parent objects has already been populated).

		NB: We use OrderedDictionary object in BaseDBTransfer class to organize
			our data dumping and loading sequence. This avoids Data Integrity 
			Error that occurs whenever non-existent ForeignKey relations are 
			invoked.
		'''
		all_files = self._get_files()
		for filename in all_files:
			with open(filename, 'r') as f:
				try:
					j = json.loads(f.read())
				except ValueError:
					logger.error('ValueError while decoding json file')
				deserialized = self._deserialize(j)
				if self.name == 'ProductTaxonomy':
					self._load_product_taxonomy(deserialized)
				else:
					self._load_generic(deserialized)
			self._move_file(filename)
		self._reset_autoincrementer()
			
	def _move_file(self, filename):
		'''
		Move an uploaded file to a new directory.

		NB: If files are being transferred around midnight, we should 
		expect to see two new folders.
		'''
		if 'fooreviews_data' in self.path_dump:
			ENV = 'fr_data'
		elif 'fooreviews_site' in self.path_dump:
			ENV = 'fr_site'
		date = str(datetime.now().date()).replace('-','_')
		new_dir = '{}_loaded_{}/'.format(ENV, date)
		new_path = self.path_dump + new_dir
		ch.make_directory(self.logger, new_path)
		new_filename = filename.split('/')[-1]
		new_filename = new_path + new_filename
		shutil.move(filename, new_path)
		self.logger.info('Finished moving file to {}'.format(new_path))


	def _load_generic(self, deserialized):
		for des_obj in deserialized:
			obj_id = des_obj.object.id
			if not self._object_exists(obj_id):
				des_obj.save()
				msg = 'Loaded {} object id={}'.format(self.name, obj_id)
				self.logger.info(msg)
			else:
				msg = 'Model object already exists for table={} id={}'
				self.logger.info(msg.format(self.name, obj_id))

	def _load_product_taxonomy(self, deserialized):
		'''
		Load ProductTaxonomy objects in the order in which the objects were 
		created. 

		NB: ProductTaxonomy is the only table in all of fooreviews whose 
			ForeignKey relations are self-referential. As a result, we have 
			a linked-list type of data structure. Here, we're simply attaching
			the links by first loading root links. Subsequent nodes can link 
			to roots without causing Database Integrity Error. 
		'''
		des_parent_list = []
		for des_obj in deserialized:
			parent = des_obj.object._mptt_cached_fields.get('parent')
			if not parent:
				des_parent_list.append(des_obj)

		if des_parent_list:
			# load the parents
			self._load_generic(des_parent_list)

		# load the children
		self._load_generic(deserialized)

	def _reset_autoincrementer(self):
		'''
		Call sql auto increment reset wrapper function to fix database 
		IntegrityError exceptions.
		'''
		app_name = self.model.__module__.split('.')[0]
		sar = sql_reset.SQLAutoIncrementReset(app=app_name, table=self.name)
		pk = sar.reset_autoincrementer()
		msg = 'SQL autoincrementer head for table={} set to pk={}'
		msg = msg.format(self.name, pk)
		self.logger.info(msg)



