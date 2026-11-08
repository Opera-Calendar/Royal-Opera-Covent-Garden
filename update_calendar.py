#!/usr/bin/env python3
"""Best-effort Royal Opera House event collector, with fail-closed coverage checks.

The website is not a published stable API. Review the workflow logs after first run.
"""
import json
import os
import re
import sys
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

BASE = 'https://www.rbo.org.uk'
LONDON = ZoneInfo('Europe/London')
NOW = datetime.now(LONDON)
ROOT = Path(__file__).resolve().parent
HEADERS = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36', 'Accept-Language':'en-GB,en;q=0.9'}
MONTHS = {m.lower(): i for i, m in enumerate(['January','February','March','April','May','June','July','August','September','October','November','December'],1)}
DAY = r'(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)'
DATE_RE = re.compile(rf'\b({DAY})\s+(\d{{1,2}})\s+({'|'.join(MONTHS)}),?\s+(\d{{1,2}})[.:](\d{{2}})\s*(am|pm)',re.I)
SALE_RE = re.compile(r'General booking opens on\s+(\d{1,2})\s+('+'|'.join(MONTHS)+r')\s+(20\d{2})\s+at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)',re.I)
DURATION_RE = re.compile(r'(?:performance|production|event) lasts approximately\s+(?:(\d+)\s+hours?)?(?:\s+and\s+)?(?:(\d+)\s+minutes?)?',re.I)


def fetch(url):
    r = requests.get(url, headers=HEADERS, timeout=35)
    r.raise_for_status()
    return r.text


def discover():
    """Gather production links from live listing and any public sitemap pages."""
    links=set()
    pages=[BASE+'/tickets-and-events']
    # Sitemap index can change; nonfatal.
    try:
        sm=fetch(BASE+'/sitemap.xml')
        urls=re.findall(r'<loc>(.*?)</loc>',sm)
        for url in urls[:40]:
            if '/production/' in url:
                links.add(url.split('?')[0])
            elif 'sitemap' in url:
                try:
                    sub=fetch(url)
                    links.update(u.split('?')[0] for u in re.findall(r'<loc>(.*?)</loc>',sub) if '/production/' in u)
                except Exception as e: print('WARN sitemap:',e)
    except Exception as e: print('WARN sitemap index:',e)
    for url in pages:
        try:
            soup=BeautifulSoup(fetch(url),'html.parser')
            for a in soup.find_all('a',href=True):
                if '/production/' in a['href']:
                    links.add(urljoin(BASE,a['href']).split('?')[0])
        except Exception as e: print('WARN listing:',e)
    # A handful of verified current pages provide fallback coverage if website listing changes.
    links.update(BASE+'/production/'+p for p in [
        'aida-robert-carsen','the-magic-flute-david-mcvicar','hercules-barrie-kosky',
        'carmen-damiano-michieletto','il-trittico-richard-jones'])
    return sorted(u for u in links if urlparse(u).netloc in ('www.rbo.org.uk','rbo.org.uk'))


def parse_time(hour, minute, ampm):
    hour=int(hour)%12 + (12 if ampm.lower()=='pm' else 0)
    return hour,int(minute)


def infer_year(month, day, start, end):
    """Resolve dates in the usual RBO season range; prefer explicit production range."""
    years=[]
    for y in (NOW.year-1,NOW.year,NOW.year+1,NOW.year+2,NOW.year+3):
        try: dt=date(y,MONTHS[month.lower()],int(day))
        except ValueError: continue
        if start and end and start-timedelta(days=2)<=dt<=end+timedelta(days=2):return y
        years.append((abs((dt-NOW.date()).days),y))
    return min(years)[1]


def range_from_text(text):
    # Prefer text near "Dates" and parse the last explicit four-digit year.
    m=re.search(r'\bDates\s+(\d{1,2})\s+('+'|'.join(MONTHS)+r')\s*[-–]\s*(\d{1,2})\s+('+'|'.join(MONTHS)+r')\s+(20\d{2})',text,re.I)
    if m:
        d1,mo1,d2,mo2,y=m.groups();y=int(y)
        start=date(y-1 if MONTHS[mo1.lower()]>MONTHS[mo2.lower()] else y,MONTHS[mo1.lower()],int(d1))
        return start,date(y,MONTHS[mo2.lower()],int(d2))
    m=re.search(r'\bDates\s+(\d{1,2})\s+('+'|'.join(MONTHS)+r')\s*[-–]\s*('+'|'.join(MONTHS)+r')\s+(\d{1,2}),?\s+(20\d{2})',text,re.I)
    if m:
        d1,mo1,mo2,d2,y=m.groups();y=int(y)
        return date(y-1 if MONTHS[mo1.lower()]>MONTHS[mo2.lower()] else y,MONTHS[mo1.lower()],int(d1)),date(y,MONTHS[mo2.lower()],int(d2))
    m=re.search(r'\bDates\s+(\d{1,2})\s*[-–]\s*(\d{1,2})\s+('+'|'.join(MONTHS)+r')\s+(20\d{2})',text,re.I)
    if m:
        d1,d2,mo,y=m.groups();return date(int(y),MONTHS[mo.lower()],int(d1)),date(int(y),MONTHS[mo.lower()],int(d2))
    return None,None


def ical_escape(s):
    return str(s).replace('\\','\\\\').replace('\n','\\n').replace(';','\\;').replace(',','\\,')


def fold(line):
    chunks=[]
    b=line.encode('utf-8')
    while len(b)>73:
        p=73
        while p>0 and (b[p]&0xc0)==0x80:p-=1
        chunks.append(b[:p].decode('utf-8'));b=b[p:]
    chunks.append(b.decode('utf-8'))
    return '\r\n '.join(chunks)


def calendar(name, events):
    lines=['BEGIN:VCALENDAR','VERSION:2.0','PRODID:-//Community ROH Opera Calendar//EN','CALSCALE:GREGORIAN','METHOD:PUBLISH',f'X-WR-CALNAME:{ical_escape(name)}','X-WR-TIMEZONE:Europe/London']
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    for ev in events:
        dt=ev['start']
        lines += ['BEGIN:VEVENT',f'UID:{ev["uid"]}@roh-opera-calendar',f'DTSTAMP:{stamp}',
                  f'DTSTART;TZID=Europe/London:{dt.strftime("%Y%m%dT%H%M%S")}',
                  f'DTEND;TZID=Europe/London:{ev["end"].strftime("%Y%m%dT%H%M%S")}',
                  f'SUMMARY:{ical_escape(ev["summary"])}',
                  f'LOCATION:{ical_escape("Royal Opera House, Covent Garden, London")}',
                  f'DESCRIPTION:{ical_escape(ev["description"])}',
                  f'URL:{ev["url"]}']
        for days in ev.get('alarms',[]):
            lines += ['BEGIN:VALARM','ACTION:DISPLAY',f'DESCRIPTION:{ical_escape(ev["summary"])}',f'TRIGGER:-P{days}D','END:VALARM']
        lines.append('END:VEVENT')
    lines.append('END:VCALENDAR')
    return '\r\n'.join(fold(line) for line in lines)+'\r\n'


def main():
    urls=discover()
    print('Discovered candidate production URLs:',len(urls))
    performances=[];sales=[];incomplete=[];processed=0
    # Avoid processing hundreds of historical productions from sitemap: inspect only future content.
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        context=browser.new_context(user_agent=HEADERS['User-Agent'], locale='en-GB', timezone_id='Europe/London')
        page=context.new_page()
        for url in urls[:600]:
            try:
                page.goto(url,wait_until='domcontentloaded',timeout=30000)
                page.wait_for_timeout(1100)
                text=page.locator('body').inner_text(timeout=10000)
                if re.search(r'Access Denied|Just a moment|verify you are human|enable JavaScript|403 Forbidden', text[:1200], re.I):
                    raise RuntimeError('Page blocked/challenged: '+repr(text[:250]))
                title=page.title().split('–')[0].strip() or url.rsplit('/',1)[-1]
                # Strictly exclude dance/ballet, screening-only pages and old productions.
                if not re.search(r'\bOpera and music\b',text,re.I):continue
                if 'No dates scheduled' in text:continue
                start,end=range_from_text(text)
                if end and end<NOW.date():continue
                if not start and not SALE_RE.search(text):
                    print('DEBUG No production date range or sale:',url,repr(text[:240]))
                    continue
                processed+=1
                # RBO often renders a non-interactive "Expand all dates" label AND
                # an actionable "Show all dates until ..." control. Clicking the
                # label by text alone can time out: find the actual button/anchor.
                def has_more_dates(body):
                    return bool(re.search(r"Show all dates until\s+\d", body, re.I))

                originally_collapsed = has_more_dates(text)
                if originally_collapsed:
                    # The action label may remain in the DOM after expansion.
                    # Count real date rows rather than interpreting text alone.
                    for attempt in range(4):
                        before = len(DATE_RE.findall(text))
                        clicked = False
                        for selector in (
                            'button:has-text("Show all dates")',
                            'button:has-text("Expand all dates")',
                            '[role="button"]:has-text("Show all dates")',
                            '[role="button"]:has-text("Expand all dates")',
                            'a:has-text("Show all dates")',
                        ):
                            try:
                                locator = page.locator(selector).first
                                if locator.count() and locator.is_visible():
                                    locator.click(timeout=3000)
                                    clicked = True
                                    break
                            except Exception as exc:
                                print('DEBUG click attempt:', selector, str(exc)[:110])
                        if not clicked:
                            clicked = bool(page.evaluate('''() => {
                                const nodes = [...document.querySelectorAll('button, a, [role="button"]')];
                                const match = nodes.find(e => /(?:Show all dates|Expand all dates)/i.test(e.innerText||''));
                                if (!match) return false;
                                match.click(); return true;
                            }'''))
                        page.wait_for_timeout(1300)
                        text = page.locator('body').inner_text(timeout=10000)
                        after = len(DATE_RE.findall(text))
                        print('DEBUG expansion:', url, 'attempt=', attempt+1,
                              'clicked=', clicked, 'date_rows=', before, '->', after,
                              'prompt_present=', has_more_dates(text))
                        parsed_dates=[]
                        for match in DATE_RE.finditer(text):
                            wd, dd, mon, *_ = match.groups()
                            try:
                                yy=infer_year(mon,dd,start,end)
                                candidate=date(yy,MONTHS[mon.lower()],int(dd))
                                if candidate.strftime('%A').lower()==wd.lower():
                                    parsed_dates.append(candidate)
                            except (ValueError, KeyError):
                                continue
                        # Stop once the final published date is visible; further
                        # clicks could collapse the list again.
                        if end and end in parsed_dates:
                            break
                        if not clicked:
                            break
                    final_rows=len(DATE_RE.findall(text))
                    # Conservative check; cannot prove intermediate dates complete.
                    if not (end and end in parsed_dates and final_rows >= 4):
                        incomplete.append(url)
                        print('INCOMPLETE listing:',url,'published_end=',end,
                              'last_parsed=',max(parsed_dates) if parsed_dates else None,
                              'date_rows=',final_rows)
                        continue
                durations=DURATION_RE.search(text)
                mins=(int(durations.group(1) or 0)*60+int(durations.group(2) or 0)) if durations else 0
                if mins<30:mins=180
                # Dates and cast section lies above Guidance; avoid synopsis dates.
                relevant=re.split(r'\bGuidance\b',text,maxsplit=1)[0]
                seen=set()
                for m in DATE_RE.finditer(relevant):
                    wd,d,month,h,minute,ap=m.groups()
                    year=infer_year(month,d,start,end)
                    hh,mm=parse_time(h,minute,ap)
                    dt=datetime(year,MONTHS[month.lower()],int(d),hh,mm,tzinfo=LONDON)
                    if dt.date()<NOW.date() or (start and dt.date()<start) or (end and dt.date()>end):continue
                    if dt.strftime('%A').lower()!=wd.lower():continue
                    if dt in seen:continue
                    seen.add(dt)
                    performances.append({'uid':uuid.uuid5(uuid.NAMESPACE_URL,url+dt.isoformat()).hex,'start':dt,'end':dt+timedelta(minutes=mins),'summary':title+' – Royal Opera House','description':f'Approximate duration: {mins} minutes (if published; otherwise 180-minute placeholder).\nCheck latest cast and venue on official page.','url':url})
                print('DEBUG production:',title,'range=',start,end,'parsed=',len(seen),'sale=',bool(SALE_RE.search(text)))
                if start and end and end>=NOW.date() and not seen:
                    incomplete.append(url)
                    print('INCOMPLETE no dates:',url)
                sm=SALE_RE.search(text)
                if sm:
                    d,month,y,h,mi,ap=sm.groups()
                    hh,mm=parse_time(h,mi or '00',ap)
                    when=datetime(int(y),MONTHS[month.lower()],int(d),hh,mm,tzinfo=LONDON)
                    if when>=NOW:
                        sales.append({'uid':uuid.uuid5(uuid.NAMESPACE_URL,'sale'+url+when.isoformat()).hex,'start':when,'end':when+timedelta(hours=1),'summary':'Ticket sales – '+title,'description':'General public booking begins. Confirm terms and availability at official website.','url':url,'alarms':[90,30,7,1]})
            except Exception as e:
                incomplete.append(url)
                print('WARN production:',url,repr(e)[:500])
        context.close()
        browser.close()
    # Reject incomplete runs instead of overwriting a valid existing subscription with a bad one.
    if incomplete:
        (ROOT/'incomplete_report.txt').write_text('\n'.join(incomplete)+'\n')
        raise RuntimeError(f'{len(incomplete)} production(s) incomplete or failed; calendar NOT updated. See WARN and DEBUG lines above.')
    if processed<2 or len(performances)<3:
        raise RuntimeError(f'Suspiciously little data: processed={processed}, performances={len(performances)}. Calendar NOT updated.')
    # Deduplicate same booking date as one event with titles combined.
    by_sale={}
    for sale in sales:
        key=sale['start']
        if key not in by_sale:by_sale[key]=sale
        else:
            old=by_sale[key];old['summary']='Ticket sales – multiple productions';old['description']+='\n'+sale['summary'].replace('Ticket sales – ','')+' : '+sale['url']
    performances.sort(key=lambda x:x['start']);sales=sorted(by_sale.values(),key=lambda x:x['start'])
    (ROOT/'royal-opera-house.ics').write_text(calendar('ROH – Opera Performances',performances),encoding='utf-8')
    (ROOT/'royal-opera-house-sales.ics').write_text(calendar('ROH – Ticket Sales',sales),encoding='utf-8')
    print(f'OK: {len(performances)} performances; {len(sales)} sale openings; {processed} productions reviewed')

if __name__=='__main__':main()
