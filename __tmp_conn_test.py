import psycopg2
try:
    psycopg2.connect(host='localhost', port=5432, dbname='ragdb', user='postgres', password='root')
except UnicodeDecodeError as e:
    print('encoding:', e.encoding)
    print('start:', e.start, 'end:', e.end)
    print('object repr:', repr(e.object))
