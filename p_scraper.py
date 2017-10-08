import re
import sys
import numpy
import matplotlib.pyplot as plot
from lxml import html
from lxml.etree import tostring
from itertools import chain
import os
from string import maketrans
import requests
from pdfminer.pdfinterp import PDFResourceManager, PDFPageInterpreter
from pdfminer.converter import TextConverter
from pdfminer.layout import LAParams
from pdfminer.pdfpage import PDFPage
from cStringIO import StringIO

def stringify_children(node):
    """Stolen from the internet"""
    parts = ([node.text] +
            list(chain(*([c.text, tostring(c), c.tail] for c in node.getchildren()))) +
            [node.tail])
    # filter removes possible Nones in texts and tails
    return ''.join(filter(None, parts))

def convert_pdf_to_txt(path):
    """Stolen from the internet"""
    rsrcmgr = PDFResourceManager()
    retstr = StringIO()
    codec = 'utf-8'
    laparams = LAParams()
    device = TextConverter(rsrcmgr, retstr, codec=codec, laparams=laparams)
    fp = file(path, 'rb')
    interpreter = PDFPageInterpreter(rsrcmgr, device)
    password = ""
    maxpages = 0
    caching = True
    pagenos=set()

    for page in PDFPage.get_pages(fp, pagenos, maxpages=maxpages, password=password,caching=caching, check_extractable=True):
        interpreter.process_page(page)

    text = retstr.getvalue()

    fp.close()
    device.close()
    retstr.close()
    return text

def extract_ps_from_text(text):
    """Extracts p-values from text, helper function for the below"""
    #test_string = 'Hi my name is p < 0.05, my P=0.042, so not p < 1.3e-10 or p < 1.4*10^-5' #Debugging regex string
    matches = re.findall('([pP][ \t]*([<>=])[ \t]*([\d](.[\d]*)?\*10\^-?\d*|[\d](.[\d]*)?e-?\d*|\d\.[\d]*))',text) #Regex matches p less than, greater than, or equal to, and values in decimal or scientific notation, either as 1e9 or 1*10^-9
    p_values = map(lambda x: (x[0],float(x[2]),x[1]),matches) #TODO: handle x*10^y notation
    return p_values

def extract_ps_from_pdf(url,file_dir):
    """Extracts p values from a pdf by following the link, returns list of p-values""" 
    try:
	r = requests.get(url)
    except:
	print "Error fetching file: "+url
	return []
    if r.status_code != 200:
	print "Error fetching file: "+url
	return []
    path = file_dir+'temp.pdf'
    with open(path, 'wb') as f:
	for chunk in r:
	    f.write(chunk)
    try:
	this_PDF_txt = convert_pdf_to_txt(path)
	os.remove(path) #Clean up
	return extract_ps_from_text(this_PDF_txt)
    except:
	print "Error extracting text from pdf: "+url
	return []

def extract_ps_from_html(url):
    """Extracts p values from a pdf by following the link, returns list of p-values""" 
    try:
	page = requests.get(url)
    except:
	print "Error fetching file: "+url
	return []
    return extract_ps_from_text(page.content)

def find_links(topic='',n=100):
    """Returns links to the first n (accessible) papers on a topic from google as pdf_links,html_links. Only takes papers that have a direct link from the search results (i.e. will not find papers that you have to click through a couple of links to get to."""
    page = requests.get('http://scholar.google.com/scholar?hl=en&q='+topic)
    pdf_links = []
    html_links = []
    while (len(pdf_links)+len(html_links) < n):
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
    plot.hist(ps,bins=numpy.arange(0,1,0.01))
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
    if not os.path.isdir(file_dir):
	os.mkdir(file_dir)
    pdf_links,html_links = find_links(topic,n)
    plotting_ps = []
    with open(file_dir+'results.csv','w') as results_file:
	results_file.write('URL,full statement,p value,relation\n')
	for url in pdf_links:
	    ps = extract_ps_from_pdf(url,file_dir)
	    for p in ps:
		results_file.write(url+','+p[0]+','+str(p[1])+','+p[2]+'\n')
		plotting_ps.append(p[1]) #so inefficient
	for url in html_links:
	    ps = extract_ps_from_html(url)
	    for p in ps:
		results_file.write(url+','+p[0]+','+str(p[1])+','+p[2]+'\n')
		plotting_ps.append(p[1]) #so inefficient
    plot_ps(plotting_ps)



if __name__ == "__main__":
    main()
