import gzip
gz_file = r'victory_manual_files\PriceFull7290696200003-045-202506140500-001.xml.gz'
xml_file = gz_file[:-3]
with gzip.open(gz_file, 'rb') as fin, open(xml_file, 'wb') as fout:
    fout.write(fin.read())