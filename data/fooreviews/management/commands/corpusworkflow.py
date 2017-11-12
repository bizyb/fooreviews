from django.core.management.base import BaseCommand
from services.corpus_workflow import workflow
import crawler.models as c_models
# import fooreviews.models as f_models
import ml.models as m_models
import services.loggers as loggers
logger = loggers.Loggers(__name__).get_logger() 

class Command(BaseCommand):

	def handle(self, *args, **kwargs):
		self._workflow()

	def _get_params(self):
		'''
		Construct and return parameters to be passed along to CorpusWorkflow
		to initiate all analysis steps. 
		'''
		param_dict_list = []
		merchant_set = c_models.Merchant.objects.filter(crawl=True)
		domain_set = m_models.TrainingDomain.objects.all()
		for merchant in merchant_set:
			for dom_obj in domain_set:
				params = {
						'merchant': merchant.name,
						'domain': dom_obj.domain,
						'subdomain': dom_obj.subdomain,
					}
				param_dict_list.append(params)
		# params = {
		# 	'merchant': 'Walmart',
		# 	'domain': 'Appliances',
		# 	'subdomain': 'Refrigeration',
		# }
		param_dict_list.append(params)
		return param_dict_list

	def _get_workflow_steps(self):
		'''
		Return a list of CorpusWorkflow steps to perform in order of call.
		'''
		steps = [
				# 'crawl_landing',
				# 'parse_landing',
				# 'build_urls',
				# 'crawl_corpus',
				# 'parse_corpus',
				# 'queue_urls',
				'crawl_training',

			]
		return steps


	def _workflow(self):
		params_dict_list = self._get_params()
		steps = self._get_workflow_steps()
		for params in params_dict_list:
			wf = workflow.CorpusWorkflow(**params)
			for step in steps:
				function = getattr(wf, step)
				msg = 'CorpusWorkflow: running {} params={}'.format(step, params)
				logger.info(msg)
				function()
			