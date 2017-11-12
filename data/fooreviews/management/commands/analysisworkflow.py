from django.core.management.base import BaseCommand
import copy
import fooreviews.models as f_models
import services.loggers as loggers
import time
logger = loggers.Loggers(__name__).get_logger() 
	
class Command(BaseCommand):

	def add_arguments(self, parser):
		help_step = 'Workflow steps. Here are some steps in order of '
		help_step += 'recommended execution: 1. crawl_detail, \n2. parse_detail, '
		help_step += '3. queue_review_urls, 4. crawl_reviews, 5. parse_reviews, '
		help_step += '6. nlp, 7. ml; 8. updatetopics, 9. generate_data '
		help_step += '10. summary_to_file. NB: must select analysis component '
		help_step += 'summaries before generate_data and summary_to_file. '
		help_frsku = 'Run analysisworkflow on a given frsku. One frsku at a '
		help_frsku += 'time is recommended but more than one is allowed.'
		help_train = 'Run analysisworkflow on training data. Issue domain '
		help_train += 'and subdomain as \'Domain+Subdomain\'. One domain/subdomain '
		help_train += 'pair recommended at a time but more than one is allowed.'	
		arguments = [
				{
					'argument': 'step',
					'settings': {
						'nargs': '+',
						'type': str,
						'help': help_step,
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
					'argument': '--training',
					'settings': {
						'nargs': '+',
						'type': str,
						'help': help_train,
					}
				},
				# {
				# 	'argument': '--updatetopics',
				# 	'settings': {
				# 		'action': 'store_true',
			 #            'dest': 'update_topics',
			 #            'default': False,
			 #            'help': 'Update LDA topics',
				# 	} 
				# },
		]
		for arg_dict in arguments:
			arg = arg_dict.get('argument')
			settings = arg_dict.get('settings')
			parser.add_argument(arg, **settings)


	def handle(self, *args, **kwargs):
		self.frsku = kwargs.get('frsku')
		self.training = kwargs.get('training')
		self.steps = kwargs.get('step')
		self.domains = []
		if self.training:
			self.domains = self._parse_training()
		if not self.frsku:
			self.frsku = []
		self._workflow()

		
	def _parse_training(self):
		dom_subdom_tups = []
		for dom_subdom in self.training:
			domain = dom_subdom.split('+')[0]
			subdomain = dom_subdom.split('+')[-1]
			dom_subdom_tups.append((domain, subdomain))
		return dom_subdom_tups


	def _get_params(self):
		'''
		Construct and return parameters to be passed along to AnalysisWorkflow
		to initiate all analysis steps. 
		'''
		param_dict_list = []
		for dom_subdom_tup in self.domains:
			params = {
					'training': True,
					'domain': dom_subdom_tup[0],
					'subdomain': dom_subdom_tup[1],
				}
			param_dict_list.append(params)
		for frsku in self.frsku:
			if f_models.Product.objects.filter(frsku=frsku).exists():
				params = {
						'frsku': frsku,
					}
				param_dict_list.append(params)
		return param_dict_list

	def _parse_step(self, step):
		'''
		Update workflow parameters with additional arguments.

		analyze_reviews is a two-step process. We first run nlp 
		and then ml.
		'''
		arg = ''
		if step == 'updatetopics':
			arg = 'update_topics'
		elif step == 'nlp':
			arg = 'run_nlp'
		elif step == 'ml':
			arg = 'run_ml'
		if not arg:
			# run_pre_nlp is not used anywhere; it's just there to let us know
			# that we're running pre-nlp steps if the above conditions are false
			arg = 'run_pre_nlp'
		else:
			step = 'analyze_reviews'
		return step, arg


	def _workflow(self):
		'''
		Run AnalysisWorkflow. If workflow step is review parsing, run the parser
		in a loop until all cache objects have been  parsed (or failures noted
		as such).

		NB: We're iterating the parsing process because sometimes ReviewParser
			ends prematurely. We don't really know why that is (and it's not
			worth trying to figure out the reason). 
		'''
		# This is a time-consuming import; delay it until we have to
		from services.analysis_workflow import workflow 

		ITERATIONS = 5
		params_dict_list = self._get_params()
		if self.steps:
			for step in self.steps:
				step, arg = self._parse_step(step)
				for i in range(ITERATIONS):
					for raw_params in params_dict_list:
						msg = 'Running AnalysisWorkflow: ITERATION={}\n'
						logger.info(msg.format(i))
						params = copy.deepcopy(raw_params)
						if step == 'analyze_reviews':
							params[arg] = True
						wf = workflow.AnalysisWorkflow(**params)
						function = getattr(wf, step)
						msg = 'AnalysisWorkflow: running step={} with params={}'
						msg = msg.format(step, params)
						logger.info(msg)
						function()
						logger.info('Finished step={}\n'.format(step))
					if step in ['parse_reviews', 'crawl_reviews']:
						logger.info('Entering sleep before iterating...zz..zz')
						time.sleep(30)
					else:
						break
		else:
			msg = 'Please provide a workflow step to run. Refer to the help '
			msg += 'menu for available steps'
			logger.error(msg)
		if not self.frsku:
			logger.info('----------------------------------------------------')
			logger.info('Please provide FRSKU to for preliminary steps')
			msg = 'Issue command like so: python manage.py analysisworkflow '
			msg += 'crawl_detail --frsku FRSKU'
			logger.info(msg)
			logger.info('----------------------------------------------------')
				

