import logging
logging.basicConfig(format='%(levelname)s: %(message)s', level=logging.INFO)
class Loggers(object):
	'''
	Creates module-specific loggers.

	NB: We are doing this in order to be able to control the name of the log 
	file and the directory where it's stored. 
	'''
	def __init__(self, name, **kwargs):
		self.name = name
		tokens = self.name.split('.')
		self.file = '/NON_EXISTENT_FILE_PATH'
		if tokens:
			self.file = ''
			for index, token in enumerate(tokens):
				if index != len(tokens)-1:
					# append orward slash to all tokens before the last one
					self.file += token + '/'
				else:
					self.file += token + '.log'
		self.module = tokens[-1]

	def get_logger(self):
		try:
			logger = logging.getLogger(self.module)
			logger.setLevel(logging.DEBUG)
			formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s')
			file_handler = logging.FileHandler(self.file)
			file_handler.setFormatter(formatter)
			logger.addHandler(file_handler)
		except Exception:
			msg = 'Unable to create a logger for {}'.format(self.name)
			logging.exception(msg)
		else:
			logging.info('New logger created for module={}'.format(self.name))
			return logger

