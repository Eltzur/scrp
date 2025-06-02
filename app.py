from flask import Flask, render_template, request
import csv

app = Flask(__name__)

def load_prices():
    data = []
    with open('price_comparison.csv', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            data.append(row)
    return data

# Your master branch list—now as dicts for easy city info
branches = [
    {'branch_name': 'Um-El-Fahem',      'branch_code': '001', 'city': 'Um-El-Fahem'},
    {'branch_name': 'Daburiya',         'branch_code': '002', 'city': 'Daburiya'},
    {'branch_name': 'Furidis',          'branch_code': '003', 'city': 'Furidis'},
    {'branch_name': 'Kalanswa',         'branch_code': '005', 'city': 'Kalanswa'},
    {'branch_name': 'Shefaraam',        'branch_code': '006', 'city': 'Shefaraam'},
    {'branch_name': 'Sachnin',          'branch_code': '007', 'city': 'Sachnin'},
    {'branch_name': 'Beer Sheva',       'branch_code': '008', 'city': 'Beer Sheva'},
    {'branch_name': 'Tamra',            'branch_code': '009', 'city': 'Tamra'},
    {'branch_name': 'Daliat El Carmel', 'branch_code': '010', 'city': 'Daliat El Carmel'},
    {'branch_name': 'Nazareth',         'branch_code': '012', 'city': 'Nazareth'},
    {'branch_name': 'Kassem',           'branch_code': '013', 'city': 'Kassem'},
    {'branch_name': 'Haifa',            'branch_code': '014', 'city': 'Haifa'},
    {'branch_name': 'Karmiel',          'branch_code': '015', 'city': 'Karmiel'},
    {'branch_name': 'Akko',             'branch_code': '016', 'city': 'Akko'},
    {'branch_name': 'Yafia',            'branch_code': '017', 'city': 'Yafia'},
    {'branch_name': 'TLV-Yefet',        'branch_code': '018', 'city': 'Tel Aviv'},
    {'branch_name': 'Ramla',            'branch_code': '019', 'city': 'Ramla'},
    {'branch_name': 'Basmat Tivon',     'branch_code': '027', 'city': 'Basmat Tivon'},
    {'branch_name': 'Rahat',            'branch_code': '028', 'city': 'Rahat'},
    {'branch_name': 'Nof Hagalil',      'branch_code': '031', 'city': 'Nof Hagalil'},
    {'branch_name': 'Internet',         'branch_code': '050', 'city': 'Internet'},
    {'branch_name': 'Jerusalem',        'branch_code': '200', 'city': 'Jerusalem'},
    # Add more as needed
]

@app.route("/", methods=["GET", "POST"])
def search():
    prices = load_prices()
    query = request.form.get("query", "")
    city = request.form.get("city", "")
    # === Dynamic city list from data ===
    cities = sorted(set(b['city'] for b in branches))
    # === Filter branches by selected city ===
    if city:
        city_branches = [b['branch_name'] for b in branches if b['city'] == city]
    else:
        city_branches = [b['branch_name'] for b in branches]
    # === Filter results by query ===
    filtered = prices
    if query:
        filtered = [row for row in prices if query.lower() in row['name'].lower() or query == row['code']]
    return render_template("search.html",
                           prices=filtered,
                           query=query,
                           city=city,
                           cities=cities,
                           branches=city_branches)

if __name__ == "__main__":
    app.run(debug=True)