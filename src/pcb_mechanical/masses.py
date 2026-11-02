"""Manufacturer nominal masses; units g. Tolerances are not published.

Values checked on Harwin's product pages, 2026-11-02. All unmatched parts
remain explicit screening estimates in the generated mass audit.
"""
HARWIN = {'M80-5001642': 1.238, 'M80-5002042': 1.389, 'M80-5T10442MC': 0.872}
CATALOG = {mpn: {'mass_g': mass, 'source': 'https://www.harwin.com/products/' + mpn,
                 'manufacturer': 'Harwin', 'checked': '2026-11-02'}
           for mpn, mass in HARWIN.items()}
