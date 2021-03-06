import re
import sys
import numpy
import matplotlib.pyplot as plot
from lxml import html
from lxml.etree import tostring
from itertools import chain
import os
import glob
from string import maketrans
import requests
import urllib2 # use for FTP
from pdfminer.pdfinterp import PDFResourceManager, PDFPageInterpreter
from pdfminer.converter import TextConverter
from pdfminer.layout import LAParams
from pdfminer.pdfpage import PDFPage
from cStringIO import StringIO
from bs4 import UnicodeDammit

def stringify_children(node):
    """Stolen from the internet"""
    parts = ([node.text] +
            list(chain(*([c.text, tostring(c), c.tail] for c in node.getchildren()))) +
            [node.tail])
    # filter removes possible Nones in texts and tails
    return ''.join(filter(None, parts))

def convert_pdf_to_txt(path):
    """Stolen from the internet, with minor modifications"""
    rsrcmgr = PDFResourceManager()
    retstr = StringIO()
    codec = 'utf-8'
    laparams = LAParams()
    laparams.all_texts = True
    device = TextConverter(rsrcmgr, retstr, codec=codec, laparams=laparams)
    fp = file(path, 'rb')
    interpreter = PDFPageInterpreter(rsrcmgr, device)
    password = ""
    maxpages = 0
    caching = True
    pagenos=set()

    for page in PDFPage.get_pages(fp, pagenos, maxpages=maxpages, password=password, caching=caching, check_extractable=True):
        interpreter.process_page(page)

    text = retstr.getvalue()

    fp.close()
    device.close()
    retstr.close()
    # handle some codec stuff
    text = UnicodeDammit(text).unicode_markup
    return text

def extract_ps_from_text(text):
    """Extracts p-values from text, helper function for the below. Regex matches p less than, greater than, or equal to, and values in decimal or scientific notation, either as 1e9 or 1*10^-9. Handles some weird unicode characters that comparison operators sometimes get replaced as:
    \u2b0d: <
    """
    p_value_regex = u'([pP]s?[ \t]*([<>=\u2b0d])[ \t]*([\d][ ]*(.[ ]*[\d]*)?[ ]*\*10[ ]*\^[ ]*-?[ ]*\d*|[\d][ ]*(.[ ]*[\d]*)?[ ]*e[ ]*-?[ ]*\d*|[\d]?[ ]*\.[ ]*[\d]*))'

    def _filter_condition(line, expression):
	#Condition(s) for filtering out non-p-value expressions that got past the regex, e.g. table keys
	if not any(re.findall('\d', expression)): # no digits?
	    return True
	if any(re.findall(u'[*.\u2020]+[ \t]*' + p_value_regex, line, re.UNICODE)): # Get rid of table and figure label entries like * p < 0.05, ** p < 0.01, etc. by looking for *, . and dagger before
	    return True
	return False

    matches = []
    for line in text.split('\n'):
	local_matches = re.findall(p_value_regex, line, re.UNICODE) 
	matches.extend([(line,) + match for match in local_matches if not _filter_condition(line, match[0])])
    def _matches_to_values(x):
	try:
	    temp = (x[0], x[1], float(x[3].replace(' ','')), x[2])
	except ValueError:
	    print("error converting value to float: ", x[3])
	    temp = (x[0], x[1], None, x[2])
	return temp 

    p_values = map(_matches_to_values, matches) #TODO: handle x*10^y notation
    return p_values

## TEST
#text = convert_pdf_to_txt('test_files/Weisbuch2009.pdf')
#print(extract_ps_from_text(text))
#exit()

def extract_ps_from_pdf(url, file_dir):
    """Extracts p values from a pdf by following the link, returns list of p-values""" 
    if url[:4] == "http":
	try:
	    if url[:4] == "http":
		s = requests.Session()
		s.headers.update({'referer': 'https://scholar.google.com'}) # some sites check
		r = s.get(url)
	except:
	    print "Error fetching file: "+url
	    return []
	if r.status_code != 200:
	    print "Error fetching file: "+url
	    return []
    elif url[:3] == "ftp":
	try:
	    r = urllib2.urlopen(url)
	except:
	    print "Error fetching file: "+url
	    return []

    path = file_dir + url.split('/')[-1]
    with open(path, 'wb') as f:
	for chunk in r:
	    f.write(chunk)


    try:
	this_PDF_txt = convert_pdf_to_txt(path)
#	os.remove(path) #Clean up
	return extract_ps_from_text(this_PDF_txt)
    except:
	print "Error extracting text from pdf: "+url
#	os.remove(path) #Clean up
	return []

def extract_ps_from_html(url):
    """Extracts p values from a pdf by following the link, returns list of p-values""" 
    try:
	s = requests.Session()
	s.headers.update({'referer': 'https://scholar.google.com'}) # some sites check
	page = s.get(url)
    except:
	print "Error fetching file: "+url
	return []
    return extract_ps_from_text(page.content)

def find_links(topic='',n=100):
    """Returns links to the first n (accessible) papers on a topic from google as pdf_links,html_links. Only takes papers that have a direct link from the search results (i.e. will not find papers that you have to click through a couple of links to get to."""
    page = requests.get('http://scholar.google.com/scholar?hl=en&q='+topic)
    pdf_links = []
    html_links = []
    while (len(pdf_links) + len(html_links) < n):
	tree = html.fromstring(page.content)
	a_tags = tree.xpath("//a")
	pdf_a_tags = filter(lambda x: x.text_content() and ("[PDF]" in x.text_content()),a_tags)
	pdf_links += map(lambda x: x.attrib['href'], pdf_a_tags)
	html_a_tags = filter(lambda x: x.text_content() and ("[HTML]" in x.text_content()),a_tags)
	html_links += map(lambda x: x.attrib['href'], html_a_tags)
	#Move to next page of search
	next_link = filter(lambda x: "gs_ico_nav_next" in stringify_children(x),a_tags)
	if next_link == []: #Out of results!
	    print "Warning: fewer papers were found than requested"
	    break
	next_link = next_link[0].attrib['href']
	page = requests.get('http://scholar.google.com'+next_link)
    return pdf_links,html_links

def plot_ps(ps):
    """Given a list of p-values, plots them on a reasonable scale"""
    bins = numpy.arange(0.0001,1.02,0.01)
    bins[0] = 0 # this plus prev. line are hacky work-around for matplotlib excluding left edge of bin 
    plot.hist(ps,bins=bins)
    plot.xlabel('p-value')
    plot.ylabel('frequency')
    plot.axvline(0.05,color='red')
    plot.show()

def main():
    """Returns p-values from the first n (accessible) papers on a topic from google as a list. Only takes papers that have a direct link from the search results (i.e. will not find papers that you have to click through a couple of links to get to."""
    if len(sys.argv) < 3:
	print 'Usage: python p_scraper.py "topic" n'
	print "(where topic is the topic for search, enclosed in quotes if there is more than one word, and n is number of papers to retrieve p-values from)"
	exit()
    topic = sys.argv[1]
    n = int(sys.argv[2])
    topic = topic.translate(maketrans(' ','+')) #Translate into a search friendly format
    file_dir = './'+topic+'/'
    if os.path.isdir(file_dir):
	files = glob.glob(file_dir + '*.*') #Clean up out of date stuff
	for f in files:
	    os.remove(f)
    else:
	os.mkdir(file_dir)
    pdf_links,html_links = find_links(topic,n)
    plotting_ps = []
    with open(file_dir+'results.csv','w') as results_file:
	results_file.write('URL,full statement,p value,relation\n')
	for url in pdf_links:
	    ps = extract_ps_from_pdf(url,file_dir)
	    for p in ps:
		this_p_raw = str(p)[1:-1]
		this_p_raw = re.sub("^u'", "'", this_p_raw)
		this_p_raw = re.sub(" u'", " '", this_p_raw) # Why can't this combine with the last line? Idk.
		results_file.write(url + ', ' + this_p_raw + '\n')
		plotting_ps.append(p[2])
	for url in html_links:
	    ps = extract_ps_from_html(url)
	    for p in ps:
		this_p_raw = str(p)[1:-1]
		this_p_raw = re.sub("^u'", "'", this_p_raw)
		this_p_raw = re.sub(" u'", " '", this_p_raw) # Why can't this combine with the last line? Idk.
		results_file.write(url + ', ' + this_p_raw + '\n')
		plotting_ps.append(p[2])
    plot_ps(plotting_ps)



if __name__ == "__main__":
    main()
