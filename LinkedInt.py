#!/usr/bin/env python3

# LinkedInt
# Scrapes LinkedIn without using LinkedIn API
# Original scraper by @DisK0nn3cT (https://github.com/DisK0nn3cT/linkedin-gatherer)
# Modified by @vysecurity
# - Additions:
# --- UI Updates
# --- Constrain to company filters
# --- Addition of Hunter for e-mail prediction


import sys
import re
import time
import requests
import subprocess
import json
import argparse

import os
import urllib.request, urllib.parse, urllib.error
import math
import string
from bs4 import BeautifulSoup

import csv as csv_module
import pdb
import ssl
import importlib
from requests.packages.urllib3.exceptions import InsecureRequestWarning


""" Setup Argument Parameters """
parser = argparse.ArgumentParser(description="Discovery LinkedIn")
parser.add_argument("-u", "--keywords", help="Keywords to search")
parser.add_argument("-o", "--output", help="Output file (do not include extentions)")
parser.add_argument("-e", "--email", help="Domain used for email address")
parser.add_argument(
    "-c", "--company", help="Restrict to company filter", action="store_true"
)
parser.add_argument("-i", "--id", help="Company ID to use")
parser.add_argument("-f", "--format", help='Email format. "auto" to search Hunter')
parser.add_argument(
    "--login",
    help="Login for LinkedIn",
)
parser.add_argument(
    "--password",
    help="Password for LinkedIn",
)
parser.add_argument(
    "--apikey",
    help="API Key for HunterIO",
)
parser.add_argument(
    "--li_at", help="Provide li_at cookie (session cookie) instead of login"
)
parser.add_argument("--proxy", help="Use proxy server")
args = parser.parse_args()

if not ((args.login and args.password) or (args.li_at)):
    print(f"Error: Either login/password or li_at cookie are required.")
    # pdb.set_trace()
    sys.exit(1)

api_key = args.apikey  # Hunter API key
username = args.login  # enter username here
password = args.password  # enter password here
if args.proxy:
    proxies = {"https": args.proxy, "http": args.proxy}
else:
    proxies = {}  # {'https':'127.0.0.1:8080'}
# silence all url warnings
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)


def create_graphql(start=0, count=50, companyId=None, title=None):
    query_string = (
        f"(start:{start},count:{count},origin:COMPANY_PAGE_CANNED_SEARCH,query:"
    )

    query_string += "(flagshipSearchIntent:SEARCH_SRP,queryParameters:List("

    params = []
    if companyId:
        params.append(
            f"(key:currentCompany,value:List({companyId})),(key:resultType,value:List(PEOPLE))"
        )
    if title:
        params.append(f"(key:title,value:List({title}))")

    query_string += ",".join(params)

    query_string += "),includeFiltersInResponse:false))&queryId=voyagerSearchDashClusters.9bce173fbce5f0cf146dac911d840d9"

    return query_string


"""
    (start:0,origin:FACETED_SEARCH,query:(flagshipSearchIntent:SEARCH_SRP,queryParameters:
    List((key:currentCompany,value:List(5470,2297043)),(key:resultType,value:List(PEOPLE)),
    (key:title,value:List(engineer))),includeFiltersInResponse:false))

    (start:0,origin:COMPANY_PAGE_CANNED_SEARCH,query:(flagshipSearchIntent:SEARCH_SRP,queryParameters:
    List((key:currentCompany,value:List({companyID})),(key:resultType,value:List(PEOPLE))
    ),includeFiltersInResponse:false))&queryId=voyagerSearchDashClusters.9bce173fbce5f0cf146dac911d840d99
"""


def login():
    s = requests.Session()
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/114.0"
    }
    res = s.get(
        "https://www.linkedin.com/uas/login",
        proxies=proxies,
        verify=False,
        headers=headers,
    )
    csrf = res.text.split('loginCsrfParam" value="')[1].split('"')[0]
    page_instance = res.text.split('pageInstance" content="')[1].split('"')[0]
    # data = res.text[res.text.find("<form"):res.text.find("</form")]

    login_data = {}

    # for c in data.split('input type')[1:]:
    #     login_data[c.split('name="')[1].split('"')[0]] = c.split('value="')[1].split('"')[0]

    login_data["session_key"] = username
    login_data["session_password"] = password
    login_data["csrfToken"] = res.cookies["JSESSIONID"]
    login_data["loginCsrfParam"] = csrf
    login_data["ac"] = "0"
    login_data["parentPageKey"] = "d_checkpoint_lg_consumerLogin"
    login_data["pageInstance"] = page_instance
    login_data["trk"] = ""
    login_data["authUUID"] = ""
    login_data["session_redirect"] = ""
    login_data["_d"] = "d"
    login_data["showGoogleOneTapLogin"] = "true"
    login_data["controlId"] = "d_checkpoint_lg_consumerLogin-login_submit_button"

    res = s.post(
        "https://www.linkedin.com/checkpoint/lg/login-submit",
        data=login_data,
        proxies=proxies,
        verify=False,
        headers=headers,
    )

    return s.cookies["li_at"]


def loadPage(client, url, data=None):
    try:
        response = client.open(url)
    except:
        print("[!] Cannot load main LinkedIn page")
    try:
        if data is not None:
            response = client.open(url, data)
        else:
            response = client.open(url)
        return "".join(response.readlines())
    except:
        sys.exit(0)


def get_search():
    body = ""
    csv = []
    css = """<style>
    #employees {
        font-family: "Trebuchet MS", Arial, Helvetica, sans-serif;
        border-collapse: collapse;
        width: 100%;
    }

    #employees td, #employees th {
        border: 1px solid #ddd;
        padding: 8px;
    }

    #employees tr:nth-child(even){background-color: #f2f2f2;}

    #employees tr:hover {background-color: #ddd;}

    #employees th {
        padding-top: 12px;
        padding-bottom: 12px;
        text-align: left;
        background-color: #4CAF50;
        color: white;
    }
    </style>

    """

    header = """<center><table id=\"employees\">
             <tr>
             <th>Photo</th>
             <th>Name</th>
             <th>Possible Email:</th>
             <th>Job</th>
             <th>Location</th>
             </tr>
             """

    # Do we want to automatically get the company ID?

    if bCompany:
        if bAuto:
            # Automatic
            # Grab from the URL
            companyID = 0
            url = (
                "https://www.linkedin.com/voyager/api/typeahead/hits?q=blended&query=%s"
                % search
            )
            headers = {
                "Csrf-Token": "ajax:0397788525211216808",
                "X-RestLi-Protocol-Version": "2.0.0",
            }
            cookies["JSESSIONID"] = "ajax:0397788525211216808"
            r = requests.get(url, cookies=cookies, headers=headers)
            content = json.loads(r.text)
            firstID = 0
            for i in range(0, len(content["elements"])):
                try:
                    companyID = content["elements"][i]["hitInfo"][
                        "com.linkedin.voyager.typeahead.TypeaheadCompany"
                    ]["id"]
                    if firstID == 0:
                        firstID = companyID
                    print("[Notice] Found company ID: %s" % companyID)
                except:
                    continue
            companyID = firstID
            if companyID == 0:
                print(
                    "[WARNING] No valid company ID found in auto, please restart and find your own"
                )
        else:
            # Don't auto, use the specified ID
            companyID = bSpecific

        print()

        print("[*] Using company ID: %s" % companyID)

    # Fetch the initial page to get results/page counts

    url = f"https://www.linkedin.com/voyager/api/graphql?variables=" + create_graphql(
        start=0, count=10, companyId=companyID, title=search
    )

    headers = {
        "Csrf-Token": "ajax:0397788525211216808",
        "X-RestLi-Protocol-Version": "2.0.0",
    }
    cookies["JSESSIONID"] = "ajax:0397788525211216808"
    # print url
    # s = requests.Session()
    # req = requests.Request(method="GET", url="https://www.linkedin.com")
    # prep = req.prepare()
    # prep.url = url

    r = requests.get(
        url,
        # params=params,
        cookies=cookies,
        headers=headers,
        verify=False,
        proxies=proxies,
    )
    content = json.loads(r.text)
    # pdb.set_trace()
    paging_data = content["data"]["searchDashClustersByAll"]["paging"]
    data_total = paging_data["total"]

    # Calculate pages off final results at 40 results/page
    pages = int(data_total / 50)

    # if pages == 0:
    #     pages = 1

    # if data_total % 40 == 0:
    #     # Becuase we count 0... Subtract a page if there are no left over results on the last page
    #     pages = pages - 1

    # if pages == 0:
    #     print("[!] Try to use quotes in the search name")
    #     sys.exit(0)

    print("[*] %i Results Found" % data_total)
    # if data_total > 1000:
    #     pages = 25
    #     print(
    #         "[*] LinkedIn only allows 1000 results. Refine keywords to capture all data"
    #     )
    print("[*] Fetching %i Pages" % pages)
    print()
    csvfile = open("{}.csv".format(outfile), "w")
    csvwriter = csv_module.writer(
        csvfile, delimiter=",", quotechar='"', quoting=csv_module.QUOTE_MINIMAL
    )

    for p in range(0, data_total, 50):
        # Request results for each page using the start offset
        url = (
            f"https://www.linkedin.com/voyager/api/graphql?variables="
            + create_graphql(start=p, count=50, companyId=companyID, title=search)
        )

        # if bCompany == False:
        #     url = (
        #         "https://www.linkedin.com/voyager/api/search/cluster?count=40&guides=List()&keywords=%s&origin=OTHER&q=guided&start=%i"
        #         % (search, p * 40)
        #     )
        # else:
        #     url = f"https://www.linkedin.com/voyager/api/graphql?variables=(start:{p},count:50,origin:COMPANY_PAGE_CANNED_SEARCH,query:(flagshipSearchIntent:SEARCH_SRP,queryParameters:List((key:currentCompany,value:List({companyID})),(key:resultType,value:List(PEOPLE))),includeFiltersInResponse:false))&queryId=voyagerSearchDashClusters.9bce173fbce5f0cf146dac911d840d99"

        #     # url = (
        #     #     "https://www.linkedin.com/voyager/api/search/cluster?count=40&guides=List(v->PEOPLE,facetCurrentCompany->%s,title->%s)&origin=OTHER&q=guided&start=%i"
        #     #     % (companyID, search, p * 40)
        #     # )
        # # print url
        r = requests.get(
            url,
            cookies=cookies,
            headers=headers,
            verify=False,
            proxies=proxies,
            # params=params,
        )
        content = r.text.encode("UTF-8")
        content = json.loads(content)

        items = []

        for d in content["data"]["searchDashClustersByAll"]["elements"]:
            for item in d["items"]:
                if item["item"]["entityResult"]:
                    items.append(item)

        print("[*] Fetching page %i with %i results" % ((p / 50), len(items)))

        for c in items:
            # if (
            #     "com.linkedin.voyager.search.SearchProfile" in c["hitInfo"]
            #     and c["hitInfo"]["com.linkedin.voyager.search.SearchProfile"][
            #         "headless"
            #     ]
            #     == False
            # ):
            if 1 == 1:
                # try:
                #     data_industry = c["hitInfo"][
                #         "com.linkedin.voyager.search.SearchProfile"
                #     ]["industry"]
                # except:
                data_industry = ""
                name = c["item"]["entityResult"]["title"]["text"]

                data_firstname = name.split(" ")[0]
                data_lastname = (
                    " ".join(name.split(" ")[1:]) if name.count(" ") > 0 else ""
                )
                data_slug = c["item"]["entityResult"]["navigationContext"]["url"]

                data_occupation = c["item"]["entityResult"]["primarySubtitle"]["text"]

                data_location = c["item"]["entityResult"]["secondarySubtitle"]["text"]
                # pdb.set_trace()
                try:
                    data_picture = c["item"]["entityResult"]["image"]["attributes"][0][
                        "detailData"
                    ]["nonEntityProfilePicture"]["vectorImage"]["artifacts"][0][
                        "fileIdentifyingUrlPathSegment"
                    ]

                except:
                    print(
                        "[*] No picture found for %s %s, %s"
                        % (data_firstname, data_lastname, data_occupation)
                    )
                    data_picture = ""

                # incase the last name is multi part, we will split it down
                # Also trying to strip out anything after a comma, and any
                # word that is all caps, since those are probably certs
                # (CPA, CFA, CISSP, etc, etc, etc)

                parts = []
                for p in data_lastname.split(",")[0].split(" "):
                    if p.upper() != p:
                        parts.append(p)

                name = data_firstname + " " + data_lastname
                fname = ""
                mname = ""
                lname = ""

                if len(parts) == 1:
                    fname = data_firstname.split(" ")[0]
                    mname = "?"
                    lname = parts[0]
                elif len(parts) == 2:
                    fname = data_firstname.split(" ")[0]
                    mname = parts[0]
                    lname = parts[1]
                elif len(parts) >= 3:
                    fname = data_firstname.split(" ")[0]
                    lname = parts[0]
                else:
                    fname = data_firstname.split(" ")[0]
                    lname = "?"

                fname = re.sub("[^A-Za-z]+", "", fname)
                mname = re.sub("[^A-Za-z]+", "", mname)
                lname = re.sub("[^A-Za-z]+", "", lname)

                if len(fname) == 0 or len(lname) == 0:
                    # invalid user, let's move on, this person has a weird name
                    continue

                    # come here

                if prefix == "full":
                    user = "{}{}{}".format(fname, mname, lname)
                if prefix == "firstlast":
                    user = "{}{}".format(fname, lname)
                if prefix == "firstmlast":
                    user = "{}{}{}".format(fname, mname[0], lname)
                if prefix == "flast":
                    user = "{}{}".format(fname[0], lname)
                if prefix == "first.last":
                    user = "{}.{}".format(fname, lname)
                if prefix == "fmlast":
                    user = "{}{}{}".format(fname[0], mname[0], lname)
                if prefix == "lastfirst":
                    user = "{}{}".format(lname, fname)
                if prefix == "first":
                    user = "{}".format(fname)
                if prefix == "firstl":
                    user = "{}{}".format(fname, lname[0])

                email = "{}@{}".format(user, suffix)

                body += (
                    "<tr>"
                    '<td><a href="%s"><img src="%s" width=200 height=200></a></td>'
                    '<td><a href="%s">%s</a></td>'
                    "<td>%s</td>"
                    "<td>%s</td>"
                    "<td>%s</td>"
                    "<a>"
                    % (
                        data_slug,
                        data_picture,
                        data_slug,
                        name,
                        email,
                        data_occupation,
                        data_location,
                    )
                )

                csv.append(
                    '"%s","%s","%s","%s","%s", "%s"'
                    % (
                        data_firstname,
                        data_lastname,
                        name,
                        email,
                        data_occupation,
                        data_location.replace(",", ";"),
                    )
                )
                foot = "</table></center>"
                f = open("{}.html".format(outfile), "w")
                f.write(css)
                f.write(header)
                f.write(body)
                f.write(foot)
                f.close()

                csvwriter.writerow(
                    [
                        data_firstname,
                        data_lastname,
                        name,
                        email,
                        data_occupation,
                        data_location.replace(",", ";"),
                    ]
                )

            else:
                print("[!] Headless profile found. Skipping")
        print()
    csvfile.close()


def banner():
    print(
        """
        ██╗     ██╗███╗   ██╗██╗  ██╗███████╗██████╗ ██╗███╗   ██╗████████╗
██║     ██║████╗  ██║██║ ██╔╝██╔════╝██╔══██╗██║████╗  ██║╚══██╔══╝
██║     ██║██╔██╗ ██║█████╔╝ █████╗  ██║  ██║██║██╔██╗ ██║   ██║   
██║     ██║██║╚██╗██║██╔═██╗ ██╔══╝  ██║  ██║██║██║╚██╗██║   ██║   
███████╗██║██║ ╚████║██║  ██╗███████╗██████╔╝██║██║ ╚████║   ██║   
╚══════╝╚═╝╚═╝  ╚═══╝╚═╝  ╚═╝╚══════╝╚═════╝ ╚═╝╚═╝  ╚═══╝   ╚═╝   
"""
    )

    # print("\033[1;31m%s\033[0;0m" % data)
    # print("\033[1;34mProviding you with Linkedin Intelligence")
    # print("\033[1;32mAuthor: Vincent Yiu (@vysec, @vysecurity)\033[0;0m")
    # print("\033[1;32mOriginal version by @DisK0nn3cT\033[0;0m")


def authenticate():
    try:
        session = login()
        if len(session) == 0:
            sys.exit("[!] Unable to login to LinkedIn.com")
        print("[*] Obtained new session")
        cookies = dict(li_at=session)
    except Exception as e:
        sys.exit("[!] Could not authenticate to linkedin. %s" % e)
    return cookies


if __name__ == "__main__":
    banner()
    # Prompt user for data variables
    search = (
        args.keywords
        if args.keywords != None
        else input("[*] Enter search Keywords (use quotes for more precise results)\n")
    )
    print()
    outfile = (
        args.output
        if args.output != None
        else input("[*] Enter filename for output (exclude file extension)\n")
    )
    print()

    while True:
        if args.company:
            bCompany = "y"
            args.company = None
        else:
            bCompany = input("[*] Filter by Company? (Y/N): \n")
        if bCompany.lower() == "y" or bCompany.lower() == "n":
            break
        else:
            print("[!] Incorrect choice")

    if bCompany.lower() == "y":
        bCompany = True
    else:
        bCompany = False

    bAuto = True
    bSpecific = 0
    prefix = ""
    suffix = ""

    print()

    if bCompany:
        while True:
            if args.id:
                if args.id == "auto":
                    bSpecific = ""
                else:
                    bSpecific = args.id
                args.id = None
            else:
                bSpecific = input(
                    "[*] Specify a Company ID (Provide ID or leave blank to automate): \n"
                )

            if bSpecific != "":
                bAuto = False
                if bSpecific != 0:
                    try:
                        int(bSpecific)
                        break
                    except:
                        print(
                            "[!] Incorrect choice, the ID either has to be a number or blank"
                        )

                else:
                    print(
                        "[!] Incorrect choice, the ID either has to be a number or blank"
                    )
            else:
                bAuto = True
                break

    print()

    while True:
        if args.email:
            suffix = args.email.lower()
            args.email = None
        else:
            suffix = input("[*] Enter e-mail domain suffix (eg. contoso.com): \n")
            suffix = suffix.lower()
        if "." in suffix:
            break
        else:
            print("[!] Incorrect e-mail? There's no dot")

    print()

    while True:
        if args.format:
            prefix = args.format.lower()
            args.format = None
        else:
            prefix = input(
                "[*] Select a prefix for e-mail generation (auto,full,firstlast,firstmlast,flast,first.last,fmlast,lastfirst): \n"
            )
            prefix = prefix.lower()
        print()
        if (
            prefix == "full"
            or prefix == "firstlast"
            or prefix == "firstmlast"
            or prefix == "flast"
            or prefix == "first"
            or prefix == "first.last"
            or prefix == "fmlast"
            or prefix == "lastfirst"
            or prefix == "firstl"
        ):
            break
        elif prefix == "auto":
            # if auto prefix then we want to use hunter IO to find it.
            print("[*] Automaticly using Hunter IO to determine best Prefix")
            url = (
                "https://hunter.io/trial/v2/domain-search?offset=0&domain=%s&format=json"
                % suffix
            )
            r = requests.get(url)
            content = json.loads(r.text)
            if "status" in content:
                print("[!] Rate limited by Hunter IO trial")
                url = "https://api.hunter.io/v2/domain-search?domain=%s&api_key=%s" % (
                    suffix,
                    api_key,
                )
                # print url
                r = requests.get(url)
                content = json.loads(r.text)
                if "status" in content:
                    print("[!] Rate limited by Hunter IO Key")
                    continue
            # print content
            prefix = content["data"]["pattern"]
            print("[!] %s" % prefix)
            if prefix:
                prefix = prefix.replace("{", "").replace("}", "")
                if (
                    prefix == "full"
                    or prefix == "firstlast"
                    or prefix == "firstmlast"
                    or prefix == "flast"
                    or prefix == "first"
                    or prefix == "first.last"
                    or prefix == "fmlast"
                    or prefix == "lastfirst"
                    or prefix == "firstl"
                ):
                    print("[+] Found %s prefix" % prefix)

                    break
                else:
                    print(
                        "[!] Automatic prefix search failed, please insert a manual choice"
                    )
                    continue
            else:
                print(
                    "[!] Automatic prefix search failed, please insert a manual choice"
                )
                continue
        else:
            print(
                "[!] Incorrect choice, please select a value from (auto,full,firstlast,firstmlast,flast,first.last,fmlast)"
            )

    print()

    # URL Encode for the querystring
    if bCompany:
        search = urllib.parse.quote(search)
    else:
        search = urllib.parse.quote_plus(search)

    if args.li_at:
        cookies = {"li_at": args.li_at}
    else:
        cookies = authenticate()

    # Initialize Scraping
    get_search()

    print("[+] Complete")
