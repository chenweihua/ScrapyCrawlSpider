from scrapy.http.request.form import FormRequest
from scrapy.linkextractors import LinkExtractor
from scrapycrawlspider.items import *
from scrapycrawlspider.loaders import *
from scrapy.spiders import CrawlSpider as BaseSpider, signals
from scrapy_splash import SplashRequest
from scrapy import Request
import json
from furl import furl


def load_dict(x):
    if x is None or isinstance(x, dict):
        return x
    try:
        return json.loads(x)
    except:
        return {}


def load_list(x):
    if x is None or isinstance(x, list):
        return x
    try:
        return json.loads(str)
    except:
        return []


class Rule(object):
    def __init__(self, link_extractor, method='GET', data=None, params=None, headers=None,
                 callback=None, cb_kwargs=None, follow=None, priority=0, dont_filter=False,
                 meta=None, proxy=None, render=False, dont_redirect=None, dont_retry=None,
                 handle_httpstatus_list=None, handle_httpstatus_all=None,
                 dont_cache=None, dont_obey_robotstxt=None,
                 download_timeout=None, max_retry_times=None,
                 process_links=None, process_request=lambda x: x):
        self.link_extractor = link_extractor
        self.callback = callback
        self.method = method
        self.data = load_dict(data)
        self.params = load_dict(params)
        self.headers = load_dict(headers)
        self.priority = priority
        self.dont_filter = dont_filter
        self.meta = load_dict(meta) or {}
        self.cb_kwargs = cb_kwargs or {}
        self.proxy = proxy
        self.render = render
        self.dont_redirect = dont_redirect
        self.dont_retry = dont_retry
        self.handle_httpstatus_list = load_list(handle_httpstatus_list)
        self.handle_httpstatus_all = handle_httpstatus_all
        self.dont_cache = dont_cache
        self.dont_obey_robotstxt = dont_obey_robotstxt
        self.download_timeout = download_timeout
        self.max_retry_times = max_retry_times
        self.process_links = process_links
        self.process_request = process_request
        if follow is None:
            self.follow = False if callback else True
        else:
            self.follow = follow


class CrawlSpider(BaseSpider):
    name = None
    
    def start_requests(self):
        self.crawler.signals.connect(self.make_requests, signal=signals.spider_idle)
        return []
    
    def make_requests(self):
        for request in self.start():
            self.crawler.engine.slot.scheduler.enqueue_request(request)
    
    def start(self):
        for url in self.make_start_urls():
            yield Request(url)
    
    def make_start_urls(self):
        return self.start_urls
    
    def splash_request(self, request, args=None):
        args = args if args else {'wait': 1, 'timeout': 30}
        meta = request.meta
        meta.update({'url': request.url})
        return SplashRequest(url=request.url, dont_process_response=True, args=args, callback=request.callback,
                             meta=meta)
    
    def _generate_request(self, index, rule, link):
        """
        generate request by rule
        :param index: rule index
        :param rule: rule object
        :param link: link object
        :return: new request object
        """
        url = furl(link.url).add(rule.params).url if rule.params else link.url
        if rule.method == 'POST':
            r = FormRequest(url=url, formdata=rule.data, headers=rule.headers, priority=rule.priority,
                            dont_filter=rule.dont_filter, callback=self._response_downloaded)
        else:
            r = Request(url=url, method=rule.method, headers=rule.headers, priority=rule.priority,
                        dont_filter=rule.dont_filter, callback=self._response_downloaded)
        r.meta.update(**rule.meta)
        r.meta.update(rule=index, link_text=link.text)
        meta_items = ['dont_redirect', 'dont_retry', 'handle_httpstatus_list', 'handle_httpstatus_all',
                      'dont_cache', 'dont_obey_robotstxt', 'download_timeout', 'max_retry_times', 'proxy', 'render']
        meta_args = {meta_item: getattr(rule, meta_item) for meta_item in meta_items if
                     not getattr(rule, meta_item) is None}
        
        r.meta.update(**meta_args)
        return r
    
    def _requests_to_follow(self, response):
        """
        requests to follow
        :param response:
        :return:
        """
        seen = set()
        for index, rule in enumerate(self._rules):
            links = [lnk for lnk in rule.link_extractor.extract_links(response)
                     if lnk not in seen]
            if links and rule.process_links:
                links = rule.process_links(links)
            for link in links[0:2]:
                seen.add(link)
                r = self._generate_request(index, rule, link)
                yield rule.process_request(r)


class ChinaSpider(CrawlSpider):
    name = 'china'
    allowed_domains = ['tech.china.com']
    start_urls = ['https://tech.china.com/articles/']
    
    rules = (
        Rule(LinkExtractor(allow='article\/.*\.html',
                           restrict_xpaths='//div[@id="left_side"]//div[@class="con_item"]'),
             render=True, callback='parse_item'),
        Rule(LinkExtractor(restrict_xpaths='//div[@id="pageStyle"]//a[contains(., "下一页")]'))
    )
    
    def parse_item(self, response):
        request = response.request
        print('Request:', request.url, vars(request))
        loader = ChinaLoader(item=NewsItem(), response=response)
        loader.add_xpath('title', '//h1[@id="chan_newsTitle"]/text()')
        loader.add_value('url', response.url)
        loader.add_xpath('text', '//div[@id="chan_newsDetail"]//text()')
        loader.add_xpath('datetime', '//div[@id="chan_newsInfo"]/text()', re='(\d+-\d+-\d+\s\d+:\d+:\d+)')
        loader.add_xpath('source', '//div[@id="chan_newsInfo"]/text()', re='来源：(.*)')
        loader.add_value('website', '中华网')
        yield loader.load_item()
