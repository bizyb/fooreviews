# set encoding to utf-8
import sys
reload(sys)
sys.setdefaultencoding("utf-8")

import copy
import dateutil.parser as date_parser
import fooreviews.models as f_models
import json
import ml.models as m_models
import random
import services.loggers as loggers
logger = loggers.Loggers(__name__).get_logger()

class GraphingData(object):
    '''
    Retrieves and formats data for visualizing in Highcharts. 

    Because we're plotting multiple charts on the same page, all the variables
    need to be passed in at the same time. This enevitably leads to collisions.
    We want to avoid that by assigning unique codes to the variables.
    Codes appended to variable names:
            done HPL - Helpful
            done - VPR - Verified Purchase
            done RCD - Recommend
            done RDT - Rating Distribution 
            done TSR - Time Series 
            done CLF - Classification
            done ASR - Aspect Rating
            done REG - Linear Regression 
            done TDS - Topic Distribution Summ
            done TDA - Topic Distribution All

        NB: Adjusted Rating is also part of the data but it's left out here because 
            it's a single data point. We'll pass it to ArticleDetailView as is.
    '''
    def __init__(self, slug, **kwargs):
        self.slug = slug
        self.frsku = kwargs.get('frsku')
        self.article = kwargs.get('article')
        self.data_obj = self._get_data()

        # set data retrieval keys
        self.tds_key = 'Topic Distribution Summ'
        self.tda_key = 'Topic Distribution All'
        self.asr_key = 'Aspect Rating'
        self.tsr_key = 'Time Series'
        self.rdt_key = 'Rating Distribution'
        self.clf_key = 'Classification'
        self.rcd_key = 'Recommend'
        self.vpr_key = 'Verified Purchase'
        self.hpl_key = 'Helpful'
        self.reg_key = 'Regression'
        self.adj_key = 'Adjusted Rating'

        self._set_colors()
        

    def _get_data(self):
        data_obj = None
        try:
            if not self.frsku:
                self.frsku = f_models.Product.objects.filter(slug=self.slug)[0].frsku
            data_obj = m_models.Data.objects.filter(frsku=self.frsku)[0]
        except Exception as e:
            msg = '{}: {}'.format(type(e).__name__, e.args[0])
            logger.exception(msg)
        return data_obj

    def _get_rand_color(self, current_list):
        '''
        Return a random, unique 6-digit hex color code 
        '''
        vals = [0,1,2,3,4,5,6,7,8,9,'A','B','C','D','E','F']
        vals = [str(v).lower() for v in vals]
        while True:
            color = '#{}'.format(''.join([random.choice(vals) for i in range(6)]))
            if color not in current_list:
                return color

    def _set_tds_colors(self):
        '''
        Set colors for TDS and TDA; TDS has 10 unique colors and one 
        additional color for the group 'Other'; In TDA, the 20 from
        TDS retain their colors but all others inherit the color from
        'Other'. We adjust the brightness of the inherited colors
        to provide a slight contrast when we later plot a detailed version. 
        (The number 20 comes from the top 10 most positive and top 10 most
        negative topics we summarized).
        '''

        color_list = []
        tds = self.data_obj.data.get(self.tds_key)
        tda = self.data_obj.data.get(self.tda_key)
        for i in range(len(tda)):
            color =  self._get_rand_color(color_list)
            color_list.append(color)
        tds, tda = self._populate_distro_colors(tds, tda, color_list)
        self.data_obj.data[self.tds_key] = tds
        self.data_obj.data[self.tda_key] = tda
        
    def _set_asr_colors(self):
        asr = self.data_obj.data.get(self.asr_key)
        for aspect_rating_dict in asr:
            rating = aspect_rating_dict['Aspect Rating']
            lum_r, lum_g = self._get_lum_factor(rating)
            sentiment = self._get_sentiment(rating)
            color = self._adjust_brightness(lum_r=lum_r, lum_g=lum_g)
            aspect_rating_dict['color'] = color
            aspect_rating_dict['sentiment'] = sentiment
        self.data_obj.data[self.asr_key] = asr
        self.data_obj.lock_colors_ASR = True
        
    def _set_tsr_colors(self):
        tsr = self.data_obj.data.get(self.tsr_key)
        color_list = []
        for i in range(len(tsr)):
            color =  self._get_rand_color(color_list)
            color_list.append(color)
        for index, key in enumerate(tsr):
            tsr[key]['color'] = color_list[index]
        self.data_obj.data[self.tsr_key] = tsr
        
    def _set_rdt_colors(self):
        rdt = self.data_obj.data.get(self.rdt_key)
        for i in range(len(rdt)):
            key = '{} Star'.format(unicode(i+1)) 
            if i != 0:
                key = key.replace('Star', 'Stars')

            # set the luminescence values, 1 star = red, 5 stars = green
            lum_g = (i+1)/float(6)
            lum_r = 1.0 - lum_g
            color = self._adjust_brightness(lum_r=lum_r, lum_g=lum_g)
            d = rdt[key]
            d['color'] = color
        self.data_obj.data[self.rdt_key] = rdt

    def _set_clf_colors(self):
        clf = self.data_obj.data.get(self.clf_key)
        for classification, val_dict in clf.items():
            if classification == 'Duplicate':
                color = '#f79b81' # fooreviews theme color
            elif classification == 'Legitimate':
                leg_count = val_dict['review_count']
                total = sum([v['review_count'] for k,v in clf.items()])

                # set the luminescence value to be ADJUSTMENT times less than 
                # what it would have been if the legitimate revie proportion had
                # been used as its green luminescence factor
                ADJUSTMENT = 1.3
                lum_g = float((leg_count/float(ADJUSTMENT*total)))
                lum_r = 1.0 - lum_g
                color = self._adjust_brightness(lum_r=lum_r, lum_g=lum_g)
            elif classification == 'Spam':
                color = '#ff0000'
            val_dict['color'] = color
        self.data_obj.data[self.clf_key] = clf

    def _get_sentiment(self, rating):
        '''
        Return a qualitative sentiment for a given a rating.
        '''
        if rating >= 4.4:
            sentiment = 'Very Positive'
        elif rating >= 3.9:
            sentiment = 'Somewhat Positive'
        elif rating >= 3.5:
            sentiment = 'Neutral'
        elif rating >= 3.0:
            sentiment = 'Somewhat Negative'
        else:
            sentiment = 'Very Negative'
        return sentiment

    def _set_donut_colors(self, key):

        # applies to RCD, VPR, HPL
        data_dict = self.data_obj.data.get(key)
        for k, val_dict in data_dict.items():
            if k in ['Recommended', 'Verified Purchase', 'Helpful']:
                color = '#2fa636' # green
            elif k in ['Not Recommended', 'Unverified Purchase', 'Unhelpful']:
                color = '#ff0000'
            val_dict['color'] = color
        self.data_obj.data[key] = data_dict

    def _set_colors(self):
        '''
        Set colors for plotting. 

        Django calls ArticleDetailView  every time the detail page is refreshed.
        This means that plot colors would change with every page refresh. We would allow
        this to happen until we are satisfied with the plot colors and have disable 
        any further changes to the colors from the admin front-end. 

        NB: We automatically lock colors here for some of the plots. These colors are not random.
        Their luminescence factors are calculated based on certain attributes, such as star rating
        or doc2vec reliability. The rest are random and require pers   
        '''
        ALL_LOCKED = True
        if not self.data_obj.lock_colors_TDS:
            self._set_tds_colors()
            ALL_LOCKED = False

        if not self.data_obj.lock_colors_ASR:
            self._set_asr_colors()
            ALL_LOCKED = False

        if not self.data_obj.lock_colors_TSR:
            self._set_tsr_colors()
            ALL_LOCKED = False

        if not self.data_obj.lock_colors_RDT:
            self._set_rdt_colors()
            self.data_obj.lock_colors_RDT = True

        if not self.data_obj.lock_colors_CLF:
            self._set_clf_colors()
            self.data_obj.lock_colors_CLF = True
        
        if not self.data_obj.lock_colors_RCD:
            self._set_donut_colors(self.rcd_key)
            self.data_obj.lock_colors_RCD = True

        if not self.data_obj.lock_colors_VPR:
            self._set_donut_colors(self.vpr_key)
            self.data_obj.lock_colors_VPR = True

        if not self.data_obj.lock_colors_HPL:
            self._set_donut_colors(self.hpl_key)
            self.data_obj.lock_colors_HPL = True
        if ALL_LOCKED:
            self.data_obj.all_colors_locked = True
        self.data_obj.save()

    def _populate_distro_colors(self, tds, tda, color_list):
        # NB: We've done away with the 'Other' group as of 10/14/17 so it 
        # does not apply

        color_other = '#000000'
        for index, distro_dict in enumerate(tda):

            # TODO: make sure final aspect labels are unique per domain 
            distro_dict['color'] = color_list[index]
            aspect_name = distro_dict.get('Aspect')
            if aspect_name == 'Other':
                color_other = color_list[index]
            for tda_dict in tda:
                for k,v in tda_dict.items():
                    if k == 'Aspect' and v == aspect_name:
                        tda_dict['color'] = color_list[index]

        # populate tda aspect colors if they haven't inherited from tds
        # color_brighter = self._adjust_brightness(color_str=color_other)
        # for tda_dict in tda:
        #     if 'summ_component' not in tda_dict.keys():
        #         tda_dict['color'] = color_brighter
        #         tda_dict ['other'] = True
        return tds, tda

    def _adjust_brightness(self, color_str='#', lum=0.25, lum_r=0.0, lum_g=0.0):
        '''
        Increase the brightness of a given color by lum, where the default
        luminosity change is +5%. 
        '''
        color_str = color_str.replace('#','')
        new_color = '#'
        RGB_MAX = 255
        if lum_r or lum_g:
            r = int(RGB_MAX*lum_r)
            g = int(RGB_MAX*lum_g)
            b = 0
            rgb = map(lambda c: str(hex(c)).replace('0x', ''), [r, g, b])
            for index, val in enumerate(rgb):
                if val == '0':
                    rgb[index] = '00'
            new_color = '#{}'.format(''.join(rgb))
            return new_color
        for i in range(len(color_str)):

            # split the color code into three pairs and get their RGBs and 
            # compute a new luminosity; limit the final rgb component values 
            # to fall within 0 to 255. 
            if i % 2 == 0:
                rgb_component = int(color_str[i:i+2], 16)
                rgb_component = int(rgb_component * (1+lum))
                if rgb_component > RGB_MAX:
                    rgb_component = RGB_MAX
                hex_str = str(hex(rgb_component)).replace('0x', '')
                new_color += hex_str
        return new_color

    def _topic_distro(self, tds=False, tda=False):
        '''
        Return topic distribution data for pie chart plotting.
        '''
        if tds:
            topic_distro_list = self.data_obj.data.get(self.tds_key)
            title = {
                'text': 'Distribution of Analyzed Topics'
            }
        elif tda:
            topic_distro_list = self.data_obj.data.get(self.tda_key)
            title = {
                'text': 'Distribution of Topics Discovered'
            }
        series = []

        # append the data in a 'sorted' order so that aspects belonging
        # to 'Other' are grouped into the same region of the pie chart
        # when plotting TDA
        series_other = []
        for distro_dict in topic_distro_list:
                series_dict = {
                    'name': str(distro_dict['Aspect']),
                    'y': distro_dict['Distribution'],
                    'color': str(distro_dict['color']),
                }
                if distro_dict.get('other'):
                    series_other.append(series_dict)
                else:
                    series.append(series_dict)
        series.extend(series_other)
        if tds:
            kwargs = {
                'chartID_TDS': 'topic-distro-TDS',
                'data_TDS': series,
                'title_TDS': title,
            }
        elif tda:
            kwargs = {
                'chartID_TDA': 'topic-distro-TDA',
                'data_TDA': series,
                'title_TDA': title,
            }

        return kwargs

    def _asr(self):
        '''
        Return aspect rating data for bubble chart plotting.

        Colors: 
            rating >= 4.0: greenish
            rating < 4.0 : redish (more like orangish)
        Color variation is determinied by a luminosity factor that depends on 
        how much the ratings deviate from the cutoff.

        '''
        aspect_rating_list = self.data_obj.data.get(self.asr_key)
        series = []
        title = {
                'text': 'Aspect Ratings and Sentiments'
            }

        series = []
        for aspect_rating_dict in aspect_rating_list:
            series_dict = {
                'name': str(aspect_rating_dict['Aspect']),
                'x': aspect_rating_dict['Rank'],
                'y': aspect_rating_dict['Aspect Rating'],
                'z': aspect_rating_dict['Weight'],
                'sentiment': str(aspect_rating_dict['sentiment']),

            }
            inner_series = {
                'data': [series_dict],
                'color': str(aspect_rating_dict['color']),
            }
            series.append(inner_series)
        kwargs = {
                'chartID_ASR': 'aspect-rating-sentiment-ASR',
                'data_ASR': series,
                'title_ASR': title,
                
            }
        return kwargs
    def _get_lum_factor(self, rating):
        '''
        Return a luminosity factor to scale red and green rgb components. 

        In order to calculate the luminosity factor, we first define a base 
        color with rgb = 255, 0, 0 (red), belonging to mimimum aspect rating of 
        1.0. we then determine the deviation from MIN_RATING 
        '''
        if rating <= 2.5:
            # anything below 2.5 should be full red
            return 1.0, 0.0
        elif rating >= 4.8:
            # anything above 4.8 should be full green
            return 0.0, 1.0
        else:
            MAX_DEVIATION = 3.0
            MIN_DEVIATION = 0.0
            MIN_RATING = 2.0
            deviation = rating - MIN_RATING
            lum_factor_green = round(deviation/float(MAX_DEVIATION), 2)
            lum_factor_red = 1.0 - lum_factor_green
            return lum_factor_red, lum_factor_green

    def _tsr(self):
        '''
        Return review time series data with aggregated number of reviews per 
        month.
        '''

        agged_dict = self.data_obj.data.get(self.tsr_key)
        mixed_keys = agged_dict.get('Overall').keys()
        mixed_keys.remove('color')
        mixed_keys = self._sort_date_objects(mixed_keys)
        tooltip_dates = self._get_tsr_xAxis(mixed_keys)
        series = []
        title = {
                'text': 'Number of Reviews Submitted Over Time'
            }
        for i in range(len(agged_dict)):
            if i == 0:
                rating = 'Overall'
                count_date_dict = agged_dict.get('Overall')
            else:
                rating = unicode(i)
                count_date_dict = agged_dict.get(rating)
            data = []
            for index, date in enumerate(mixed_keys):
                review_count = count_date_dict.get(date)
                color = count_date_dict.get('color') 
                data.append(review_count)
            if rating != 'Overall':
                rating = int(rating)
            inner_series = {
                'data': data,
                'name': rating,
                'color': str(color),
            }
            series.append(inner_series)
        TSR_interval = self._tsr_x_interval(series)
        kwargs = {
                'chartID_TSR': 'time-series-TSR',
                'data_TSR': series,
                'title_TSR': title, 
                'dates_TSR': tooltip_dates,
                'TSR_interval': TSR_interval,   
            }
        return kwargs

    def _tsr_x_interval(self, series):
        '''
        Determine the tick interval for a TSR data series so that plotted data 
        always have a maximum number of NUM_INTERVALS so that there's no crowding.
        '''
        NUM_INTERVALS = 10
        tick_interval = 1
        data = series[0].get('data')
        num_datapoints = len(data)
        if num_datapoints > NUM_INTERVALS:
            # round to the nearest ten
            num_datapoints = int(round(num_datapoints, -1))
            tick_interval = num_datapoints/NUM_INTERVALS
        return tick_interval





    def _sort_date_objects(self, date_str_list):
        # sort the dates
        date_objects = [date_parser.parse(d) for d in date_str_list]
        date_objects.sort()
        date_str_list = ['{}/{}/{}'.format(d.date().month, d.date().day,\
                     d.date().year) for d in date_objects]
        return date_str_list
    def _get_tsr_xAxis(self, date_str_list):
        # return dates as Sep 2017, etc.
        months = {
                1: 'Jan', 
                2: 'Feb', 
                3: 'Mar', 
                4: 'Apr', 
                5: 'May', 
                6: 'Jun', 
                7: 'Jul', 
                8: 'Aug', 
                9: 'Sep',
                10: 'Oct',
                11: 'Nov',
                12: 'Dec'
        }
        tooltip_dates = []
        for d in date_str_list:
            date_tokens = d.split('/')
            month = date_tokens[0] 
            year = date_tokens[-1]
            tooltip_dates.append('{} {}'.format(months[int(month)], year))
        return tooltip_dates

    def _reg(self):
        '''
        Return regression data.

        Regression data is only for internal use.
        '''
        reg_dict = self.data_obj.data.get(self.reg_key)
        self.data_obj.lock_colors_REG = True
        self.data_obj.save()
        series = []
        title = {
                'text': 'working title: regression'
            }
        slope = float(reg_dict.get('slope'))
        intercept = float(reg_dict.get('intercept'))
        r_squared = float(reg_dict.get('r_squared'))
        x = [float(val) for val in reg_dict.get('x')]
        y = [float(val) for val in reg_dict.get('y')]
        z = [str(val) for val in reg_dict.get('z')]
        for index, values in enumerate(zip(x,y,z)):
            series_dict = {
                'x': values[0],
                'y': values[1],
                'label': values[2],

            }
            series.append(series_dict)

        kwargs = {
                'chartID_REG': 'regression-REG',
                'data_REG': series,
                'title_REG': title,    
        }
        return kwargs

    def _donut(self, rdt=False, clf=False, rcd=False, vpr=False, hpl=False):
        '''
        Return plotting data for donut chart plotting. Donut charts apply to 
        RDT, CLF,RCD, VPR,  
        '''
        # TODO: refactor code by donut type
        if rdt:
            # rating distro
            star_count_dict = self.data_obj.data.get(self.rdt_key)
            title = {
                    'text': 'Distribution of Reviews by Star Rating'
                }
        elif clf:
            # spam/duplicate/legitimate classification
            star_count_dict = self.data_obj.data.get(self.clf_key)
            title = {
                    'text': 'Classification of Reviews'
                }
        elif rcd:
            # recommended/not recommended
            star_count_dict = self.data_obj.data.get(self.rcd_key)
            title = {
                    'text': 'Review Recommendation'
                }
        elif vpr:
            # verified purchase
            star_count_dict = self.data_obj.data.get(self.vpr_key)
            title = {
                    'text': 'Purchase Type'
                }
        elif hpl:
            star_count_dict = self.data_obj.data.get(self.hpl_key)
            title = {
                    'text': 'Helpfulness of Reviews'
                }

        series = []
        for i in range(len(star_count_dict)):
            if rdt:
                key = '{} Star'.format(unicode(i+1)) 
                if i != 0:
                    key = key.replace('Star', 'Stars')
            elif clf:
                # we don't really need to assign the key like this but 
                # we'll follow the pattern for rdt
                if i == 0:
                    key = 'Duplicate'
                elif i == 1: 
                    key = 'Legitimate'
                elif i == 2:
                    key = 'Spam'
            elif rcd:
                if i == 0:
                    key = 'Recommended'
                elif i == 1:
                    key = 'Not Recommended'
            elif vpr:
                if i == 0:
                    key = 'Verified Purchase'
                elif i == 1:
                    key = 'Unverified Purchase'
            elif hpl:
                if i == 0:
                    key = 'Helpful'
                elif i == 1:
                    key = 'Unhelpful'
            review_count = star_count_dict.get(key)['review_count']

            # separate count by a commas if greater than three digits
            yString = '{0:,}'.format(review_count)
            tooltip_header = 'Number of Reviews'
            if key in ['Helpful', 'Unhelpful']:
                tooltip_header = 'Number of People'
            legend_name = key.replace('Purchase', '')
            series_dict = {
                    'name': legend_name,
                    'y': review_count,
                    'yString': yString,
                    'header': tooltip_header,
                    'color': str(star_count_dict.get(key)['color'])
                }

            series.append(series_dict)
        if rdt:
            kwargs = {
                    'chartID_RDT': 'rating-distribution-RDT',
                    'data_RDT': series,
                    'title_RDT': title,     
                }
        elif clf:
            kwargs = {
                'chartID_CLF': 'rating-classification-CLF',
                'data_CLF': series,
                'title_CLF': title,     
            }
        elif rcd:
            kwargs = {
                'chartID_RCD': 'review-recommendation-RCD',
                'data_RCD': series,
                'title_RCD': title,     
            }
        elif vpr:
            kwargs = {
                'chartID_VPR': 'verified-purchase-VPR',
                'data_VPR': series,
                'title_VPR': title,     
            }
        elif hpl:
            kwargs = {
                'chartID_HPL': 'helpful-reviews-HPL',
                'data_HPL': series,
                'title_HPL': title,     
            } 
        return kwargs

    def _adj(self):
        '''
        Return adjusted product rating.
        '''
        adjusted_rating = self.data_obj.data.get(self.adj_key)
        return {'adj': adjusted_rating }

    def _unicode_to_str(self, d):
        '''
        Perform recursive type casting of unicode objects to str so that 
        Javascript can handle the data properly.

        NB: There's no easy way around this since Highcharts or JS can't handle
            unicode strings with the u' prefix. 
        '''
        for k,v in d.items():
            v = d.pop(k)
            if isinstance(k, unicode):
                k = str(k)
            if isinstance(v, unicode):
                v = str(v)
            elif isinstance(v, dict):
                self._unicode_to_str(v)
            elif isinstance(v, list):
                for index, val in enumerate(v):
                    if isinstance(val, dict):
                        self._unicode_to_str(val)
                    elif isinstance(val, unicode):
                        val = str(val)
                        v[index] = val
            d[k] = v
        return d

    def _get_from_db(self):
        '''
        Query the database for formatted plotting data.
        ''' 
        lookup = {
            'data__frsku': self.frsku,
        }

        data_set = f_models.HighchartsFormattedData.objects.filter(**lookup)
        # if data_set.count() and self.data_obj.all_colors_locked:
        if data_set.exists():
            data_unicode = data_set[0].formatted_data 
            data_utf8 = json.dumps(data_unicode)
            data_utf8 = json.loads(data_utf8) 
            data_str = self._unicode_to_str(data_unicode)
            return data_str

    def _format_data(self):
        '''
        Return a newly formatted plotting data.
        '''
        # tds = self._topic_distro(tds=True)
        tda = self._topic_distro(tda=True)
        asr = self._asr()
        tsr = self._tsr()
        reg = self._reg()
        adj = self._adj()
        rdt = self._donut(rdt=True)
        clf = self._donut(clf=True)
        rcd = self._donut(rcd=True) # does not apply to Amazon, eBags
        vpr = self._donut(vpr=True)
        hpl = self._donut(hpl=True)
        kwargs_str = {
            # 'tds': tds,
            'tda': tda,
            'asr': asr,
            'tsr': tsr,
            'reg': reg,
            'adj': adj, 
            'rdt': rdt,
            'clf': clf,
            'rcd': rcd,
            'vpr': vpr,
            'hpl': hpl,
        }
        return kwargs_str

    def _save_formatted_data(self, new_data):
        '''
        Save formatted data to db.
        '''
        lookup = {
            'data__frsku': self.frsku,
        }
        params = {
                    'formatted_data': new_data,
                    'data': self.data_obj,
        }
        
        # delete any existing formatted data before saving a new entry; this
        # will be true if we decide to change some colors again after locking them
        existing_data = f_models.HighchartsFormattedData.objects.filter(**lookup)
        existing_data.all().delete()
        # save the formatted data to db once all colors have been locked
        f_models.HighchartsFormattedData.objects.create(**params)
        msg = 'Saved formatted data to HighchartsFormattedData for FRSKU={}'
        logger.info(msg.format(self.frsku))


    def get_data(self):
        '''
        Return all plottable data in their proper Highcharts format. If the data 
        haven't already been formatted, do so and save them to db. Otherwise, 
        retrieve the formatted set (not reformatting the data every new request
        and page refresh save us 40-50 percent in response time).

        NB: We're not plotting regression data since it's only for internal use.
        '''
        kwargs = {}
        try: 
            kwargs_str = self._get_from_db()
            if not kwargs_str or not self.article.context_upto_date:
                kwargs_str = self._format_data()
                self._save_formatted_data(kwargs_str)
            kwargs = {}
            # kwargs.update(kwargs_str.get('tds')) #do not enable tds; we haven't fixed 
            # tds dictionary indexing after moving to tda so keep getting KeyError
            kwargs.update(kwargs_str.get('tda'))
            kwargs.update(kwargs_str.get('asr'))
            kwargs.update(kwargs_str.get('tsr'))
            kwargs.update(kwargs_str.get('rdt'))
            kwargs.update(kwargs_str.get('clf'))
            # kwargs.update(kwargs_str.get('rcd'))
            # kwargs.update(kwargs_str.get('vpr'))
            # kwargs.update(kwargs_str.get('hpl'))
            kwargs['adjusted_rating'] = kwargs_str.get('adj').get('adj')
            return kwargs
        except Exception as e:
            msg = '{}: {}'.format(type(e).__name__, e.args[0])
            logger.exception(msg)



