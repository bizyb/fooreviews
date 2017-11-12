from django import template
register = template.Library()

@register.simple_tag
def get_dict_item(dictionary, **kwargs):
	'''
	Given a dictionary and a key, return the corresponding value. 
	'''
	request = kwargs.get('request')
	key = kwargs.get('key')
	if key and request:
		inner_dict = dictionary.get(key)
		if inner_dict:
			return inner_dict.get(request)
		


