from django.db import connection

class SQLAutoIncrementReset(object):
	'''
	Resets the SQL autoincrementer in postgres.

	In postgres (and presumably in other SQL databases) the autoincrementer
	loses track of the highest primary key when db objects are both created 
	and loaded. When they're created, the autoincrementer assigns the next 
	available integer value. When the data is loaded instead, the loaded, 
	deserialized object already has its own primary key. Somehow this leads 
	to the autoincrementer losing track of its place. When we later try to 
	create new objects and assign primary keys automatically, we get 
	Database IntegrityError exception. We solve this issue by explicilty 
	telling the database to reset it since there's no way of doing it through
	Django. (Our initial solution called for doing this through the psql shell.
	However, since we have a few dozen tables and constatly move data around,
	we have to reset the incrementer after every loaddata operation). 

	'''
	def __init__(self, *args, **kwargs):
		self.app_name = kwargs.get('app')
		self.table_name = kwargs.get('table')
 
	def reset_autoincrementer(self):
		table_name = '{}_{}'.format(self.app_name, self.table_name.lower())
		query = "SELECT setval(\'"+table_name+"_id_seq\', max(id)) from " + table_name
		cursor = connection.cursor()
		cursor.execute(query)
		pk = cursor.fetchone()[0]
		return pk