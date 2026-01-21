"""
Onshape API client with HMAC authentication.
"""
import os
import hashlib
import hmac
import base64
import datetime
import random
import string
from urllib.parse import urlencode, urlparse
import requests
from dotenv import load_dotenv

load_dotenv()


class OnshapeClient:
    """Client for interacting with the Onshape REST API."""
    
    def __init__(self):
        self.access_key = os.getenv('ONSHAPE_ACCESS_KEY')
        self.secret_key = os.getenv('ONSHAPE_SECRET_KEY')
        self.base_url = os.getenv('ONSHAPE_API_URL', 'https://cad.onshape.com')
        
        if not self.access_key or not self.secret_key:
            raise ValueError("ONSHAPE_ACCESS_KEY and ONSHAPE_SECRET_KEY must be set")
    
    def _make_nonce(self) -> str:
        """Generate a random 25-character nonce."""
        chars = string.ascii_lowercase + string.digits
        return ''.join(random.choice(chars) for _ in range(25))
    
    def _make_auth_headers(self, method: str, path: str, query: dict = None) -> dict:
        """
        Create Onshape API authentication headers using HMAC.
        
        See: https://onshape-public.github.io/docs/auth/apikeys/
        """
        method = method.upper()
        date = datetime.datetime.utcnow().strftime('%a, %d %b %Y %H:%M:%S GMT')
        nonce = self._make_nonce()
        content_type = 'application/json'
        
        # Build query string
        query_string = ''
        if query:
            query_string = urlencode(query)
        
        # Build the string to sign per Onshape docs:
        # method\nnonce\ndate\ncontent-type\npath\nquery\n (with trailing newline)
        # The ENTIRE string must be lowercase
        string_to_sign = (
            f"{method}\n"
            f"{nonce}\n"
            f"{date}\n"
            f"{content_type}\n"
            f"{path}\n"
            f"{query_string}\n"
        ).lower()
        
        # Create HMAC signature
        signature = hmac.new(
            self.secret_key.encode('utf-8'),
            string_to_sign.encode('utf-8'),
            hashlib.sha256
        ).digest()
        signature_b64 = base64.b64encode(signature).decode('utf-8')
        
        # Build authorization header
        auth_header = f"On {self.access_key}:HmacSHA256:{signature_b64}"
        
        return {
            'Authorization': auth_header,
            'Date': date,
            'On-Nonce': nonce,
            'Content-Type': content_type,
            'Accept': 'application/json'
        }
    
    def get(self, path: str, query: dict = None) -> dict:
        """Make an authenticated GET request to the Onshape API."""
        headers = self._make_auth_headers('GET', path, query)
        url = f"{self.base_url}{path}"
        if query:
            url += '?' + urlencode(query)
        
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()
    
    def get_binary(self, path: str, query: dict = None) -> bytes:
        """Make an authenticated GET request that returns binary data.
        
        Handles 307 redirects by re-authenticating for the redirect URL.
        """
        headers = self._make_auth_headers('GET', path, query)
        headers['Accept'] = 'application/octet-stream'
        url = f"{self.base_url}{path}"
        if query:
            url += '?' + urlencode(query)
        
        # Don't follow redirects automatically
        response = requests.get(url, headers=headers, allow_redirects=False)
        
        # Handle 307 redirect (Onshape redirects to regional servers)
        if response.status_code == 307:
            redirect_url = response.headers.get('Location')
            if redirect_url:
                # Parse the redirect URL and re-authenticate
                parsed = urlparse(redirect_url)
                redirect_path = parsed.path
                redirect_query = {}
                if parsed.query:
                    for pair in parsed.query.split('&'):
                        if '=' in pair:
                            k, v = pair.split('=', 1)
                            redirect_query[k] = v
                
                # Create new headers for the redirect URL
                redirect_headers = self._make_auth_headers('GET', redirect_path, redirect_query if redirect_query else None)
                redirect_headers['Accept'] = 'application/octet-stream'
                
                response = requests.get(redirect_url, headers=redirect_headers)
        
        response.raise_for_status()
        return response.content
    
    # Assembly API methods
    def get_assembly_definition(self, did: str, wid: str, eid: str, 
                                include_mate_features: bool = True,
                                include_mate_connectors: bool = True) -> dict:
        """
        Get the definition of an assembly.
        
        Returns parts, sub-assemblies, instances, and optionally mate features.
        """
        path = f"/api/v6/assemblies/d/{did}/w/{wid}/e/{eid}"
        query = {
            'includeMateFeatures': str(include_mate_features).lower(),
            'includeMateConnectors': str(include_mate_connectors).lower(),
            'includeNonSolids': 'true'
        }
        return self.get(path, query)
    
    def get_assembly_features(self, did: str, wid: str, eid: str) -> dict:
        """Get all features in an assembly (mates, patterns, etc.)."""
        path = f"/api/v6/assemblies/d/{did}/w/{wid}/e/{eid}/features"
        return self.get(path)
    
    def get_assembly_bom(self, did: str, wid: str, eid: str) -> dict:
        """Get the Bill of Materials for an assembly."""
        path = f"/api/v6/assemblies/d/{did}/w/{wid}/e/{eid}/bom"
        return self.get(path)
    
    # Part Studio API methods
    def get_mass_properties(self, did: str, wid: str, eid: str, 
                            part_id: str = None) -> dict:
        """
        Get mass properties for parts in a part studio.
        
        Returns mass, volume, center of mass, inertia tensor.
        """
        path = f"/api/v6/partstudios/d/{did}/w/{wid}/e/{eid}/massproperties"
        query = {}
        if part_id:
            query['partId'] = part_id
        return self.get(path, query if query else None)
    
    def get_parts(self, did: str, wid: str, eid: str) -> dict:
        """Get all parts in a part studio."""
        path = f"/api/v6/partstudios/d/{did}/w/{wid}/e/{eid}/parts"
        return self.get(path)
    
    def get_part_mass_properties(self, did: str, wid: str, eid: str, 
                                  part_id: str) -> dict:
        """Get mass properties for a specific part."""
        path = f"/api/v6/parts/d/{did}/w/{wid}/e/{eid}/partid/{part_id}/massproperties"
        return self.get(path)
    
    # Document API methods
    def get_document(self, did: str) -> dict:
        """Get document metadata."""
        path = f"/api/v6/documents/d/{did}"
        return self.get(path)
    
    def get_document_elements(self, did: str, wid: str) -> dict:
        """Get all elements (tabs) in a document workspace."""
        path = f"/api/v6/documents/d/{did}/w/{wid}/elements"
        return self.get(path)
    
    # Export methods
    def export_stl(self, did: str, wid: str, eid: str, part_id: str = None,
                   units: str = 'meter', mode: str = 'binary') -> bytes:
        """Export part(s) as STL."""
        if part_id:
            path = f"/api/v6/parts/d/{did}/w/{wid}/e/{eid}/partid/{part_id}/stl"
        else:
            path = f"/api/v6/partstudios/d/{did}/w/{wid}/e/{eid}/stl"
        query = {'units': units, 'mode': mode}
        return self.get_binary(path, query)
