import requests, re, json, pytz, time, sys
from datetime import datetime

# The default name of the file generated unless an argument is passed to the script
OUTPUT_FILE_NAME = "afd_mtr.json"
NWS_DISCUSSION_URL = "https://forecast.weather.gov/product.php?site=NWS&issuedby=MTR&product=AFD&format=CI&version=1&glossary=0"

def NWS_timestamp_to_unix(dstr):
    #Converts a date in the format "1028 PM PST Sun Nov 29 2020" to a UNIX timestamp
    dstr = dstr.upper()
    months = ['JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC']
    tokens = dstr.split()
    PM = bool(tokens[1] == "PM")
    tstr = tokens[0]
    hour = int(tstr[0]) if len(tstr) == 3 else int(tstr[0:2])
    hour = hour+12 if PM and hour < 12 else hour
    minute = int(tstr[-2:])
    year = int(tokens.pop())
    day = int(tokens.pop())
    month = months.index(tokens.pop())+1
    tz = pytz.timezone('America/Los_Angeles')
    dt = tz.localize(datetime(year, month, day, hour, minute, 0))
    return int(dt.timestamp())

def create_json(rawtext):
    output_json = {}
    forecast_credits = {}
    social_media_urls = []
    web_url = re.compile(r"(w{3}\.)?[a-zA-Z0-9\-]+\.[A-Za-z]{3}")

    dollar_split = rawtext.split('$$')
    credits_lines = dollar_split[1].splitlines()

    for c_line in credits_lines:
        if re.match(r"^[A-Z\s]+\.{3}", c_line) != None:
            credit = c_line.split('...')
            forecast_credits[credit[0].lower()] = credit[1].replace('.', '')
            continue
        if re.match(web_url, c_line):
            social_media_urls.append(c_line)

    output_json['discussion'] = {}
    output_json['metadata'] = {}
    output_json['metadata']['credits'] = forecast_credits
    output_json['metadata']['urls'] = social_media_urls
    output_json['metadata']['file_created'] = {
        'timestamp': datetime.now().strftime("%c"),
        'timestamp_unix': round(time.time())
        }

    sections = dollar_split[0].split("&&")
    
    # Recently updated sections
    updated_line = re.search(r"\.{3}New ([A-Z\s,]+)\.+", sections[0])
    if updated_line != None:
        output_json['recently_updated'] = []
        for updated_section in updated_line.group(1).split(","):
            output_json['recently_updated'].append(re.sub(r"^\s+|\s+$", "", updated_section).lower())

    ## Parse the header
    discussion_timestamp = re.search(r"^\s?(\d{3,4}\s[A-Z]{2}\s[A-Z]{3}\s[A-Za-z]{3}\s[A-Za-z]{3}\s\d{1,2}\s\d{4})", sections[0], re.MULTILINE).group(1)

    output_json['metadata']['timestamp'] = discussion_timestamp
    output_json['metadata']['timestamp_unix'] = NWS_timestamp_to_unix(discussion_timestamp)
    sections[0] = re.sub(r"^[0-9]{3}[r\n][A-Z0-9\s]+[\r\n]{2}[A-Za-z\s]+[\r\n]", "", sections[0])
    sections[0] = re.sub(r"^[0-9A-Za-z\s\.',]+(\.[A-Z-0-9\s]+\.{3})", "\g<1>", sections[0])

    ### Parse individual sections of the discussion ###
    timeframe = re.compile(r"\(.+\)") # e.g. "(Tonight through Sunday)"

    for section in sections:
        if (re.search(r"^\s+$", section) != None or section.find(".MTR ")) > -1:
            continue
        section = re.sub(r"^\s+|\s+$", "", section)
        subsections = section.split("\n\n")
        section_title = ""
        text_sections = [] # Array of the individual paragraphs of main body text
        
        for subsection in subsections:
            if re.search(r"\.[A-Z\s]+\.{3}", subsection) != None:
                subsection_info = subsection.split("\n")
                section_title = subsection_info[0].replace(".", "").lower()
                output_json['discussion'][section_title] = {}
                for header_line in subsection_info[1:]:
                    # If it's a timeframe
                    if (re.search(timeframe, header_line) != None):
                        output_json['discussion'][section_title]['timeframe'] = re.sub(r"[\(\)]", "", header_line)
                        continue
                    # If it's a timestamp e.g. "Issued at 1030 AM PST Sat Feb 1 2025"
                    if (header_line.find('Issued at') > -1):
                        timestamp = header_line.replace("Issued at ", "")
                        output_json['discussion'][section_title]['timestamp'] = timestamp
                        output_json['discussion'][section_title]['timestamp_unix'] = NWS_timestamp_to_unix(timestamp)

                output_json['discussion'][section_title]['recently_updated'] = ('recently_updated' in output_json and section_title in output_json['recently_updated'])
                continue

            # Now parse the main body text of the section
            subsection = subsection.replace("\n", " ")
            subsection = subsection.replace("`", "'")
            text_sections.append(subsection.replace("  ", " "))
        ## Now join the paragraphs back together
        output_json['discussion'][section_title]['text'] = "\n\n".join(text_sections)

    return output_json

def main():

    forecast_json = {}
    print("\n> Attemping to reach forecast.weather.gov...")
    r = requests.get(NWS_DISCUSSION_URL)

    if r.status_code != 200:
        forecast_json["error"] = f"Request to {NWS_DISCUSSION_URL} returned status {r.status_code}."
        return json.dumps(forecast_json)
    forecast_text = re.search(r"<pre class=\"glossaryProduct\">(.+)<\/pre>", r.text, re.DOTALL).group(1)
    
    forecast_json = create_json(forecast_text)
    # If an argument is passed to the script use that as the file name
    newfile = sys.argv[1] if len(sys.argv) > 1 else OUTPUT_FILE_NAME
    with open(newfile, "w") as json_file:
        json_file.write(json.dumps(forecast_json))
        print("> File written! "+OUTPUT_FILE_NAME)

if __name__ == "__main__":
    main()
