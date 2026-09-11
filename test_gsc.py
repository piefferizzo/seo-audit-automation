from google.oauth2 import service_account
from googleapiclient.discovery import build

SERVICE_ACCOUNT_FILE = 'credentials/service-account.json'
SCOPES = ['https://www.googleapis.com/auth/webmasters.readonly']

credentials = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE,
    scopes=SCOPES
)

service = build('searchconsole', 'v1', credentials=credentials)

# Prova diversi formati di URL
urls_to_test = [
    'sc-domain:arkys.agency',
    'https://arkys.agency',
    'https://www.arkys.agency'
]

for site_url in urls_to_test:
    try:
        response = service.sites().get(siteUrl=site_url).execute()
        print(f"✅ Accesso riuscito per: {site_url}")
        print(f"   Permesso: {response.get('permissionLevel')}")
    except Exception as e:
        print(f"❌ Errore per {site_url}: {str(e)[:100]}")