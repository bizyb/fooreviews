from django.utils.text import slugify
from dateutil import parser as date_parser
import services.loggers as loggers
logger = loggers.Loggers(__name__).get_logger()

class FormatArticle(object):
    '''
    Formats article content for populating the DetailView template.
    '''
    def __init__(self, article_obj, **kwargs):
        self.article = article_obj
        self.aspect_anchors_list = []

    def _get_key_specs(self):
        '''
        Return product key specs in a list format.
        '''
        key_specs_raw = self.article.product.key_specs.split(';')
        
        # delete any empty elements
        key_specs_cleaned = [val for val in key_specs_raw if val]
        return key_specs_cleaned

    def _get_pricing(self):
        '''
        Return the most recent price list. Go through the price JSON object,
        which uses the date the prices were updated, and format the return 
        object like so: {merchant: {rating:x, price:y}}
        '''
        # TODO: untested
        # TODO: the price JSON does not have the product URL
        try:
            price_json = self.article.product.price
            unsorted_dates_str = price_json.keys()
            unsorted_dates_datetime = []
            for d in unsorted_dates_str:
                parsed = date_parser.parse(d)
                unsorted_dates_datetime.append(parsed)
            sorted_dates = sorted(unsorted_dates_datetime)
            target_date_datetime = sorted_dates[-1]
            target_date_str = target_date_datetime.ctime()
            kwargs = {
                        'date': target_date_datetime, 
                        'price_list': price_json.get(target_date_str)
                    }
            return kwargs
        except Exception as e:
            msg = '{}: {}'.format(type(e).__name__, e.args[0])
            logger.exception(msg)

    def _get_star_rating(self, adjusted_rating):
        '''
        Construct an image of a star rating corresponding to adjusted_rating. Return
        a set of sequential image URLs to represent the rating pictorially. 
        '''
        # round to the nearest quareter
        rounded_rating = round(adjusted_rating*4)/4
        remainder_str = str(rounded_rating).split('.')[-1]
        remainder_float = rounded_rating - int(rounded_rating)
        base_path = '''<img src="/static/img/star-rating/star-{}.png">'''
        star_rating = ''
        # do some sanity check first before appending any stars
        if rounded_rating <= 5.0:
            for i in range(int(rounded_rating)):
                star_rating += base_path.format(100)
            if remainder_float > 0.0:
                if remainder_float == 0.5:
                    remainder_str = '50'
                star_rating += base_path.format(remainder_str)
        return star_rating

    def _aspect_anchor_tags(self, aspect, bulk=False):
        '''
        Construct pairs of aspect name and aspect ID tags for HTML 
        embedding. The ID tags are used as anchor tags in the table of contents.
        '''
        return slugify(aspect)

    
    def update_article(self):
        '''
        Update the contents of an article object with the 
        start rating image URLs.

        Each topical anlysis in the content should containt the
        following:
            1. the analysis text
            2. aspect name
            3. aspect rating
            4. color 
                a. the color has already been calculated and saved 
                    in the HighchartsFormattedData table.
                b. we use the color as part of inline CSS to color-code
                    blocks of text with a left-side border
            5. star rating image URLs
            6. anchor tag
        '''
        if self.article.content:
            aspect_list = []
            frsku = self.article.product.frsku
            nested_content_list = self.article.content.get(frsku)
            for topical_dict in nested_content_list:
                for aspect, content_dict in topical_dict.items():
                    anchor_tag = self._aspect_anchor_tags(aspect)
                    aspect_list.append({aspect: anchor_tag})
                    if not self.article.context_upto_date:
                        if 'aspect_star_rating' in content_dict.keys():
                            rating = content_dict.get('aspect_rating')
                            star_image_path = self._get_star_rating(rating)
                            content_dict['aspect_star_rating'] = star_image_path
                            content_dict['anchor_tag'] = anchor_tag
                            topical_dict[aspect] = content_dict

            if not self.article.context_upto_date:
                # update article content
                self.article.content = {frsku: nested_content_list}
                self.article.save()
            self.aspect_anchors_list = aspect_list

    def _disabled_plots(self):
        '''
        Return the status of donut plots that may have been optionally 
        enabled/disabled based on their relevance and fitness for analysis. 
        These would be review recommendation (RCD), review helpfulness (HPL),
        and purchase type (VPR).
        '''
        plot_status_dict = {
            'disable_TSR': self.article.disable_TSR,
            'disable_RCD': self.article.disable_RCD,
            'disable_VPR': self.article.disable_VPR,
            'disable_HPL': self.article.disable_HPL,
            'disable_metadata': self.article.disable_metadata,
        }
        return plot_status_dict

    def get_formatted_content(self):
        formatted_dict = {
            'key_specs': self._get_key_specs(),
            'aspect_anchor_tags': self.aspect_anchors_list, 
        }
        formatted_dict.update(self._disabled_plots())
        return formatted_dict