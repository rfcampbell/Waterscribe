"""
Fetch fish thumbnail images and species info from Wikipedia.
"""
import json
import re
import logging
from urllib.request import Request, urlopen
from urllib.parse import quote

logger = logging.getLogger(__name__)

HEADERS = {'User-Agent': 'WaterScribe/1.0 (aquarium tracker)'}


def _wiki_summary(name):
    """Fetch Wikipedia page summary for a given name."""
    try:
        url = f'https://en.wikipedia.org/api/rest_v1/page/summary/{quote(name)}'
        req = Request(url, headers=HEADERS)
        resp = json.loads(urlopen(req, timeout=5).read())
        return resp
    except Exception as e:
        logger.debug(f"Wikipedia summary failed for '{name}': {e}")
        return None


def _wiki_html(name):
    """Fetch Wikipedia page HTML (mobile-optimized, smaller) for parsing."""
    try:
        url = f'https://en.wikipedia.org/api/rest_v1/page/mobile-html/{quote(name)}'
        req = Request(url, headers=HEADERS)
        return urlopen(req, timeout=8).read().decode('utf-8', errors='ignore')
    except Exception:
        return None


def _extract_field(html, patterns):
    """Try multiple regex patterns against HTML, return first match."""
    for pat in patterns:
        m = re.search(pat, html, re.IGNORECASE | re.DOTALL)
        if m:
            # Strip HTML tags from the match
            val = re.sub(r'<[^>]+>', '', m.group(1)).strip()
            if val:
                return val
    return None


def fetch_fish_image(species, common_name=None):
    """Try to get a thumbnail URL from Wikipedia for a fish species."""
    for name in [species, common_name]:
        if not name:
            continue
        resp = _wiki_summary(name)
        if resp:
            thumb = resp.get('thumbnail', {}).get('source')
            if thumb:
                return thumb
    return None


def fetch_species_info(species, common_name=None):
    """
    Fetch species info from Wikipedia. Returns a dict with:
    - summary: text blurb
    - native_range: where the fish is from
    - biotope: habitat type
    - temp_range: preferred temperature
    - ph_range: preferred pH
    """
    info = {}
    
    # Try species name first, then common name
    for name in [species, common_name]:
        if not name:
            continue
        
        # Get summary blurb
        resp = _wiki_summary(name)
        if resp and resp.get('extract'):
            info['summary'] = resp['extract']
            
            # Try to extract location/habitat from the summary text
            text = resp['extract']
            
            # Look for native range patterns in summary
            range_patterns = [
                r'(?:native to|found in|endemic to|occurs in|distributed (?:in|throughout)|originat(?:es?|ing) (?:from|in))\s+([^.]{5,120})',
                r'(?:from|in)\s+(South America|Central America|North America|Africa|Asia|Southeast Asia|Amazon|Orinoco|[A-Z][a-z]+ (?:River|Basin|region))[^.]{0,80}',
            ]
            for pat in range_patterns:
                m = re.search(pat, text, re.IGNORECASE)
                if m:
                    info['native_range'] = m.group(1).strip().rstrip(',;')
                    break
            
            # Look for habitat/biotope clues
            habitat_patterns = [
                r'(?:inhabit(?:s|ing)?|live(?:s|ing)? in|found in|prefer(?:s|ring)?)\s+((?:slow|fast|clear|murky|black|white|shallow|deep|still|flowing)[- ]?water[^.]{0,60})',
                r'(blackwater|whitewater|clearwater|mountain stream|flood(?:ed)? forest|swamp|pond|lake|river|creek|tributary)[^.]{0,40}',
            ]
            for pat in habitat_patterns:
                m = re.search(pat, text, re.IGNORECASE)
                if m:
                    info['biotope'] = m.group(1).strip().rstrip(',;')
                    break
            
            break  # Got a summary, stop trying names
    
    # Try to get more structured data from the full page
    for name in [species, common_name]:
        if not name:
            continue
        html = _wiki_html(name)
        if not html:
            continue
        
        # Temperature
        if 'temp_range' not in info:
            temp = _extract_field(html, [
                r'(?:temperature|temp\.?)\s*(?:range)?[:\s]*(\d{1,2}\s*[-–]\s*\d{1,2}\s*°?\s*[CF])',
                r'(\d{1,2}\s*[-–]\s*\d{1,2}\s*°\s*C)',
            ])
            if temp:
                info['temp_range'] = temp
        
        # pH
        if 'ph_range' not in info:
            ph = _extract_field(html, [
                r'pH[:\s]*(\d\.?\d?\s*[-–]\s*\d\.?\d?)',
                r'(?:pH|acidity)[^.]{0,20}?(\d\.?\d?\s*[-–]\s*\d\.?\d?)',
            ])
            if ph:
                info['ph_range'] = ph
        
        # Native range from infobox if not found in summary
        if 'native_range' not in info:
            nr = _extract_field(html, [
                r'(?:Range|Distribution|Native\s+range|Habitat)[^<]*?</(?:th|td)>[^<]*<td[^>]*>(.*?)</td>',
            ])
            if nr:
                info['native_range'] = nr[:200]
        
        break
    
    return info if info else None
