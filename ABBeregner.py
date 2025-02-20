import os
from google.oauth2 import service_account
from googleapiclient.discovery import build
import requests
from datetime import datetime
import socket
import time
import hashlib
import sys

def load_config():
    try:
        with open('config.txt', 'r', encoding='utf-8') as file:
            config = {}
            for line in file:
                if '=' in line:
                    key, value = line.strip().split('=')
                    config[key.strip()] = value.strip()
            return config
    except FileNotFoundError:
        raise Exception("config.txt fil ikke fundet i samme mappe som scriptet")

def check_for_updates():
    github_url = "https://raw.githubusercontent.com/vr-autobasen/ABBeregner/refs/heads/main/ABBeregner.py"
    current_script = os.path.abspath(__file__)

    try:
        # Hent den nyeste version fra GitHub
        response = requests.get(github_url)
        if response.status_code == 200:
            online_content = response.text

            # Læs den nuværende fil
            with open(current_script, 'r', encoding='utf-8') as f:
                local_content = f.read()

            # Sammenlign ved hjælp af hash
            online_hash = hashlib.md5(online_content.encode()).hexdigest()
            local_hash = hashlib.md5(local_content.encode()).hexdigest()

            if online_hash != local_hash:
                print("Der er fundet en ny version. Opdaterer...")
                with open(current_script, 'w', encoding='utf-8') as f:
                    f.write(online_content)
                print("Opdatering gennemført. Genstarter programmet...")
                os.execv(sys.executable, ['python'] + sys.argv)
            else:
                print("Programmet er opdateret til seneste version.")
    except Exception as e:
        print(f"Kunne ikke tjekke for opdateringer: {str(e)}")




# Google Sheets setup
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
config = load_config()
SERVICE_ACCOUNT_FILE = config['SERVICE_ACCOUNT_FILE']
KM_SPREADSHEET_ID = config['KM_SPREADSHEET_ID']
TAX_SPREADSHEET_ID = config['TAX_SPREADSHEET_ID']



def get_sheets_service():
    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            creds = service_account.Credentials.from_service_account_file(
                SERVICE_ACCOUNT_FILE, scopes=SCOPES)
            service = build('sheets', 'v4', credentials=creds)
            return service.spreadsheets()
        except socket.error:
            if attempt < max_attempts - 1:
                time.sleep(2 ** attempt)
                continue
            raise


def get_eur_exchange_rate():
    url = "https://api.exchangerates.org.uk/latest"
    headers = {
        "Content-Type": "application/json"
    }

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return float(response.json()['rates']['DKK'])
    except Exception as e:
        # Hvis API'et fejler, brug en standard kurs
        return 7.4602  # Aktuel standardkurs


def fetch_hubspot_mileage(registration_number, api_key):
    url = "https://api.hubapi.com/crm/v3/objects/deals/search"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "filterGroups": [{
            "filters": [{
                "propertyName": "dealname",
                "operator": "CONTAINS_TOKEN",
                "value": registration_number.upper()
            }]
        }],
        "properties": ["dealname", "kilometer", "createdate"],
        "sorts": [{
            "propertyName": "createdate",
            "direction": "DESCENDING"
        }],
        "limit": 1
    }

    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()

        deals = response.json().get("results", [])
        if deals:
            deal = deals[0]
            return {
                "kilometer": deal.get("properties", {}).get("kilometer"),
                "deal_id": deal.get("id")  # Sikrer at vi får deal_id med
            }
        return None
    except Exception as e:
        print(f"Fejl ved hentning af kilometertal fra HubSpot: {str(e)}")
        return None


def get_vehicle_overview(registration_number, api_token):
    # Hent basis køretøjsdata
    url = f"https://api.synsbasen.dk/v1/vehicles/registration/{registration_number}"
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json"
    }

    try:
        # Hent basisdata
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        basic_data = response.json()["data"]

        # Hent motordata
        engine_url = f"{url}?expand[]=engine"
        engine_response = requests.get(engine_url, headers=headers)
        engine_response.raise_for_status()
        engine_data = engine_response.json()["data"]["engine"]

        return {
            'brand_model': f"{basic_data.get('brand', 'N/A')} {basic_data.get('model', 'N/A')}",
            'variant': basic_data.get('variant', 'N/A'),
            'body_type': basic_data.get('body_type', 'N/A'),
            'usage': basic_data.get('usage', 'N/A'),
            'first_registration_date': basic_data.get('first_registration_date', 'N/A'),
            'last_inspection_date': basic_data.get('last_inspection_date', 'N/A'),
            'last_inspection_result': basic_data.get('last_inspection_result', 'N/A'),


            'horsepower': engine_data.get('horsepower', 'N/A'),
            'leasing_period_end': basic_data.get('leasing_period_end', 'Ikke leaset')
        }
    except Exception as e:
        raise Exception(f"Fejl ved hentning af køretøjsoverblik: {str(e)}")

def fetch_basic_vehicle_data(registration_number, api_token):
    url = f"https://api.synsbasen.dk/v1/vehicles/registration/{registration_number}"
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()

        data = response.json()["data"]
        return {
            'fuel_efficiency': data.get('fuel_efficiency'),
            'fuel_type': data.get('fuel_type'),
            'registration_date': data.get('first_registration_date'),
            'model': data.get('model'),
            'version': data.get('version'),
            'brand': data.get('brand'),
            'type': data.get('kind'),
            'total_weight': data.get('total_weight')
        }
    except Exception as e:
        raise Exception(f"Fejl ved hentning af køretøjsdata: {str(e)}")


def fetch_engine_data(registration_number, api_token):
    url = "https://api.synsbasen.dk/v1/vehicles"
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json"
    }
    params = {
        "query": {
            "registration_start": registration_number
        },
        "method": "SELECT",
        "expand[]": "engine"
    }

    response = requests.post(url, headers=headers, json=params)
    return response.json()["data"][0]["engine"]


def fetch_engine_data(registration_number, api_token):
    url = f"https://api.synsbasen.dk/v1/vehicles/registration/{registration_number}?expand[]=engine"
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()

        data = response.json()["data"]
        engine_data = data.get("engine", {})
        return {
            'fuel_efficiency': engine_data.get('fuel_efficiency'),
            'fuel_type': engine_data.get('fuel_type')
        }
    except Exception as e:
        raise Exception(f"Fejl ved hentning af motordata: {str(e)}")


def fetch_weight_data(registration_number, api_token):
    url = f"https://api.synsbasen.dk/v1/vehicles/registration/{registration_number}?expand[]=weight"
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()

        data = response.json()["data"]
        weight_data = data.get("weight", {})
        return {
            'total_weight': weight_data.get('total_weight')
        }
    except Exception as e:
        raise Exception(f"Fejl ved hentning af vægtdata: {str(e)}")


def update_km_data(sheets, handelspris, norm_km, current_km):
    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            updates = [
                {'range': 'Ark1!E7', 'values': [[handelspris]]},
                {'range': 'Ark1!E8', 'values': [[norm_km]]},
                {'range': 'Ark1!E9', 'values': [[current_km]]}
            ]

            for update in updates:
                sheets.values().update(
                    spreadsheetId=KM_SPREADSHEET_ID,
                    range=update['range'],
                    valueInputOption='RAW',
                    body={'values': update['values']}
                ).execute()
            break
        except socket.error:
            if attempt < max_attempts - 1:
                time.sleep(2 ** attempt)
                continue
            raise


def fetch_evaluation_data(registration_number, api_token):
    url = f"https://api.synsbasen.dk/v1/vehicles/registration/{registration_number}?expand[]=appraisals"
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()

        appraisals = response.json().get("data", {}).get("appraisals", {})

        if not appraisals.get("service_available") or not appraisals.get("data"):
            raise Exception("Ingen vurderingsdata tilgængelig")

        # Sorter efter dato og tag den nyeste vurdering
        latest_appraisal = sorted(appraisals["data"], key=lambda x: x["date"], reverse=True)[0]

        return {
            'retail_price': latest_appraisal.get('original_price'),
            'evaluation': latest_appraisal.get('value', 0),
            'registration_tax': latest_appraisal.get('registration_tax', 0)
        }
    except Exception as e:
        raise Exception(f"Fejl ved hentning af evaluerings data: {e}")


def calculate_vehicle_age(registration_date):
    current_date = datetime.now()
    reg_date = datetime.strptime(registration_date, "%Y-%m-%d")
    return (current_date - reg_date).days // 365

def find_trade_price_based_on_age(sheets, vehicle_age):
    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            result = sheets.values().get(
                spreadsheetId=KM_SPREADSHEET_ID,
                range='Ark1!E19:I19'
            ).execute()
            values = result.get('values', [[]])[0]

            if vehicle_age < 1:
                trade_price = values[0]
                age_group = "0-1 år"
            elif 1 <= vehicle_age < 2:
                trade_price = values[1]
                age_group = "1-2 år"
            elif 2 <= vehicle_age < 3:
                trade_price = values[2]
                age_group = "2-3 år"
            elif 3 <= vehicle_age < 10:
                trade_price = values[3]
                age_group = "3-9 år"
            else:
                trade_price = values[4]
                age_group = "Over 10 år"

            return float(trade_price) * 1000, age_group
        except socket.error:
            if attempt < max_attempts - 1:
                time.sleep(2 ** attempt)
                continue
            raise

def update_co2_in_sheets(sheets, fuel_type, fuel_efficiency, registration_date, vehicle_type):
    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            if isinstance(fuel_efficiency, str):
                fuel_efficiency_formatted = fuel_efficiency.replace(".", ".")
            else:
                fuel_efficiency_formatted = str(fuel_efficiency).replace(".", ".")

            reg_date = datetime.strptime(registration_date, "%Y-%m-%d")
            wltp_cutoff_date = datetime.strptime("2017-09-01", "%Y-%m-%d")
            co2_norm = "WLTP" if reg_date >= wltp_cutoff_date else "NEDC"

            updates = [
                {'range': 'Værktøj til CO2!C26', 'values': [[co2_norm]]},
                {'range': 'Værktøj til CO2!C27', 'values': [[fuel_type]]},
                {'range': 'Værktøj til CO2!C25', 'values': [[fuel_efficiency_formatted]]}
            ]

            for update in updates:
                sheets.values().update(
                    spreadsheetId=TAX_SPREADSHEET_ID,
                    range=update['range'],
                    valueInputOption='USER_ENTERED',
                    body={'values': update['values']}
                ).execute()

            result = sheets.values().get(
                spreadsheetId=TAX_SPREADSHEET_ID,
                range='Værktøj til CO2!C30'
            ).execute()
            co2_value = result.get('values', [[0]])[0][0]

            target_range = 'Brugte Varebiler!L23' if vehicle_type == "Varebil" else 'co2km01'
            sheets.values().update(
                spreadsheetId=TAX_SPREADSHEET_ID,
                range=target_range,
                valueInputOption='USER_ENTERED',
                body={'values': [[co2_value]]}
            ).execute()
            break
        except socket.error:
            if attempt < max_attempts - 1:
                time.sleep(2 ** attempt)
                continue
            raise

def update_vehicle_data(sheets, vehicle_type, total_weight, handelspris, new_price):
    if vehicle_type == "Varebil":
        weight_category = "over 3.000 kg og som enten er åben eller uden sideruder bag føresædet" if total_weight > 3000 else "Alle andre"
        updates = [
            {'range': 'Brugte Varebiler!L21', 'values': [[str(int(handelspris))]]},
            {'range': 'Brugte Varebiler!L22', 'values': [[str(int(new_price))]]},
            {'range': 'Brugte Varebiler!L27', 'values': [[weight_category]]}
        ]
    else:
        updates = [
            {'range': 'handelspris01', 'values': [[str(int(handelspris))]]},
            {'range': 'nypris01', 'values': [[str(int(new_price))]]}
        ]

    for update in updates:
        sheets.values().update(
            spreadsheetId=TAX_SPREADSHEET_ID,
            range=update['range'],
            valueInputOption='RAW',
            body={'values': update['values']}
        ).execute()

def get_export_tax(sheets, vehicle_type):
    tax_range = 'Brugte Varebiler!G32' if vehicle_type == "Varebil" else 'finalTax01'
    result = sheets.values().get(
        spreadsheetId=TAX_SPREADSHEET_ID,
        range=tax_range
    ).execute()
    return float(result.get('values', [[0]])[0][0])

def calculate_new_price(eval_data, manual_price=None):
    if manual_price is not None:
        try:
            price = float(manual_price)
            if price <= 0:
                raise ValueError("Pris skal være større end 0")
            return price
        except ValueError:
            raise Exception("Ugyldig manuel pris indtastet")

    # Hvis ingen manuel pris, prøv at beregne automatisk
    if eval_data.get('retail_price'):
        return eval_data['retail_price']
    elif eval_data.get('evaluation') and eval_data.get('registration_tax'):
        return eval_data['evaluation'] + eval_data['registration_tax']
    else:
        return None


def get_export_tax(sheets, vehicle_type, registration_tax):
    # Hent altid eksportafgift fra sheet
    tax_range = 'Brugte Varebiler!G32' if vehicle_type == "Varebil" else 'finalTax01'
    result = sheets.values().get(
        spreadsheetId=TAX_SPREADSHEET_ID,
        range=tax_range
    ).execute()

    # Returner altid værdien fra sheetet
    return float(result.get('values', [[0]])[0][0])


def update_hubspot_deal_values(deal_id, eur_price, reduced_tax, api_key):
    if not deal_id:
        print("Ingen deal_id tilgængelig - springer HubSpot opdatering over")
        return

    url = f"https://api.hubapi.com/crm/v3/objects/deals/{deal_id}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # Konverter værdierne til strings og fjern eventuelle decimaler
    eur_price_str = str(int(float(eur_price)))
    reduced_tax_str = str(int(float(reduced_tax)))

    data = {
        "properties": {
            "estimeret_salgspris_i_euro": eur_price_str,
            "ca_eksportafgiftvurdering": reduced_tax_str
        }
    }

    try:
        response = requests.patch(url, headers=headers, json=data)
        response.raise_for_status()
        print("HubSpot deal er blevet opdateret med Euro pris og eksportafgift")
    except requests.exceptions.HTTPError as http_err:
        print(f"HTTP fejl ved opdatering af HubSpot deal: {http_err.response.text}")
    except Exception as e:
        print(f"Generel fejl ved opdatering af HubSpot deal: {str(e)}")



def log_to_file(registration_number, type, vehicle_info, new_price, export_tax, reduced_tax, handelspris_input, norm_km_input, current_km_input, sheet_handelspris, age_group, eur_price, dkk_converted, total_sum):
    if not os.path.exists('logs'):
        os.makedirs('logs')

    filename = f"logs/vehicle_export_log_{datetime.now().strftime('%Y-%m-%d')}.txt"

    try:
        with open(filename, 'r', encoding='utf-8') as f:
            entry_count = sum(1 for line in f if line.startswith('=== Log Entry'))
    except FileNotFoundError:
        entry_count = 0

    log_entry = (
        f"\n=== Log Entry #{entry_count + 1} - {datetime.now().strftime('%H:%M:%S')} ===\n"
        f"1. Nummerplade: {registration_number}\n"
        f"2. Type: {type}\n"
        f"3. Køretøj: {vehicle_info}\n"
        f"4. Indtastet handelspris: {handelspris_input:,.2f} kr.\n"
        f"5. Norm kilometer: {norm_km_input:,} km\n"
        f"6. Aktuelle kilometer: {current_km_input:} km\n"
        f"7. Handelspris fra sheet: {sheet_handelspris:,.2f} kr. ({age_group})\n"
        f"8. Nypris: {new_price:,.2f} kr.\n"
        f"9. Eksportafgift: {export_tax:.2f} kr.\n"
        f"10. Eksportafgift efter reduktion: {reduced_tax:.2f} kr.\n"
        f"11. Euro pris: {eur_price:,.2f} EUR\n"
        f"12. Omregnet til DKK: {dkk_converted:,.2f} kr.\n"
        f"13. Total sum (Reduktion + DKK): {total_sum:,.2f} kr.\n"
        f"{'=' * 50}\n"
    )

    with open(filename, 'a', encoding='utf-8') as f:
        f.write(log_entry)


def main():
    config = load_config()

    api_token = config['API_TOKEN']

    while True:
        try:
            sheets = get_sheets_service()

            # Spørg efter nummerplade
            registration_number = input("\nIndtast nummerplade (eller 'q' for at afslutte): ").strip()

            # Check om brugeren vil afslutte
            if registration_number.lower() == 'q':
                print("Afslutter programmet...")
                break
            print("Henter basis køretøjsdata...")
            basic_data = fetch_basic_vehicle_data(registration_number, api_token)
            vehicle_type = basic_data['type']

            weight_data = fetch_weight_data(registration_number, api_token)
            total_weight = weight_data.get('total_weight', 0)  # Brug 0 som default hvis ingen vægt findes

            print("Henter evalueringsdata...")
            eval_data = fetch_evaluation_data(registration_number, api_token)

            vehicle_age = calculate_vehicle_age(basic_data['registration_date'])
            print(f"Bilens alder: {vehicle_age} år")

            # I main()-funktionen, efter du har hentet registration_number
            print("\nHenter køretøjsoverblik...")
            vehicle_overview = get_vehicle_overview(registration_number, api_token)

            # Hent HubSpot kilometer
            hubspot_data = fetch_hubspot_mileage(registration_number, config['HUBSPOT_API_KEY'])
            hubspot_km = hubspot_data.get("kilometer", "N/A") if hubspot_data else "N/A"

            print("\n## Køretøjsoverblik ##")
            print(f"Bil: {vehicle_overview['brand_model']} {vehicle_overview['variant']}")
            print(f"Karosseri: {vehicle_overview['body_type']}")
            print(f"Kilometerstand (HubSpot): {hubspot_km}")
            print(f"Anvendelse: {vehicle_overview['usage']}")
            print(f"Første reg. {vehicle_overview['first_registration_date']}")

            print(f"Motor: {vehicle_overview['horsepower']} HK")
            print(f"Slagvolumen: {vehicle_overview['engine_displacement']}")
            print(f"Leaset?: {vehicle_overview['leasing_period_end']}")
            print(
                f"Sidste syn: {vehicle_overview['last_inspection_date']} - Resultat: {vehicle_overview['last_inspection_result']}")
            print("-" * 50)

            handelspris_input = float(input("Indtast handelsprisen: "))
            norm_km_input = float(input("Indtast norm km: "))

            # Erstat den eksisterende HubSpot kilometer håndtering med denne kode:
            hubspot_data = fetch_hubspot_mileage(registration_number, config['HUBSPOT_API_KEY'])
            if hubspot_data and hubspot_data.get("kilometer"):
                current_km_input = float(hubspot_data["kilometer"])
                print(f"Kilometertal hentet fra HubSpot: {current_km_input}")
            else:
                current_km_input = float(input("Indtast bilens kørte kilometer: "))

            update_km_data(sheets, handelspris_input, norm_km_input, current_km_input)
            handelspris, age_group = find_trade_price_based_on_age(sheets, vehicle_age)
            print(f"Handelspris fra sheet: {handelspris} kr. for aldersgruppen {age_group}.")

            # Find dette sted i koden hvor new_price beregnes
            new_price = calculate_new_price(eval_data)
            is_manual_price = False  # Tilføj denne variabel

            if new_price is None:
                manual_price = input("Kunne ikke beregne nypris automatisk. Indtast manuel nypris: ")
                new_price = calculate_new_price(eval_data, manual_price)
                is_manual_price = True  # Sæt til True når manuel pris er indtastet

            engine_data = fetch_engine_data(registration_number, api_token)
            update_co2_in_sheets(sheets, engine_data['fuel_type'], engine_data['fuel_efficiency'],
                                 basic_data['registration_date'], vehicle_type)

            update_vehicle_data(sheets, vehicle_type, total_weight, handelspris, new_price)

            # I main-funktionen
            registration_tax = eval_data['registration_tax']
            export_tax = get_export_tax(sheets, vehicle_type, registration_tax)

            brand = basic_data.get('brand', 'N/A')
            model = basic_data.get('model', 'N/A')
            version = basic_data.get('version', 'N/A')
            fuel_type = basic_data.get('fuel_type', 'N/A')
            vehicle_info = f"{brand} {model} {version} {fuel_type}"

            print(f"\nType: {vehicle_type}")
            if vehicle_type == "Varebil":
                print(f"Totalvægt: {total_weight} kg")
            print(f"Køretøj: {vehicle_info}")
            print(f"Nypris: {new_price:,.2f} kr.")
            print(f"Eksportafgift: {export_tax:.2f} kr.")
            reduced_tax = (export_tax * 0.85 - 3000) if export_tax > 50000 else export_tax - 11000

            print(f"Eksportafgift efter reduktion: {reduced_tax:.2f} kr.")

            # Derefter håndter euro-beregninger
            eur_price = float(input("Indtast Euro pris: "))
            exchange_rate = get_eur_exchange_rate()
            dkk_converted = eur_price * exchange_rate
            total_sum = reduced_tax + dkk_converted

            # Print euro-relaterede værdier
            print(f"\nEuro pris: {eur_price:,.2f} EUR")
            print(f"Omregnet til DKK: {dkk_converted:,.2f} kr.")
            print(f"Total sum (Reduktion + DKK): {total_sum:,.2f} kr.")

            if is_manual_price:
                print("Bemærk: KRÆVER DOBBELTTJEK")

            # Erstat denne del i main()-funktionen:
            if hubspot_data:  # Brug hubspot_data i stedet for hubspot_km
                deal_id = hubspot_data.get('deal_id')
                update_hubspot_deal_values(deal_id, eur_price, reduced_tax, config['HUBSPOT_API_KEY'])

                                           # Log alle værdier
            log_to_file(registration_number, vehicle_type, vehicle_info, new_price,
                        export_tax, reduced_tax, handelspris_input, norm_km_input,
                        current_km_input, handelspris, age_group, eur_price,
                        dkk_converted, total_sum)






        except Exception as e:
            print(f"Fejl: {e}")
            time.sleep(2)
            continue

if __name__ == "__main__":
    check_for_updates()
    main()
