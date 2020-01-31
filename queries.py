RANDOM_CITY = 'SELECT distinct(cityName) FROM HOTELS ORDER BY RAND() LIMIT 1;'


def get_hotel_city(hotel_name):
    return 'select cityName from HOTELS where hotelName = \'%s\';' % hotel_name


def get_hotel_stars(hotel_name):
    return "select stars from HOTELS where hotelName = '%s';" % hotel_name


def get_hotels_by_city(city, select, where, having, order, offset):
    return 'select id, hotelName, stars, cityName, address, price %s from HOTELS where cityName=\'%s\' %s %s order by %s price limit %s, 3;' % (select, city, where, having, order, str(offset))


def where_clause_stars(stars):
    return 'stars=%s' % stars


def get_hotel_by_id(hotel_id):
    return 'select hotelName, stars, cityName, address, countryName from HOTELS where id=%s;' % hotel_id


def get_hotels_by_distance(latitude, longitude, distance):
    return 'select ST_distance_sphere(point(longitude, latitude), point(%s, %s)) as distance, hotelName, stars, cityName, address from HOTELS having distance<%s order by distance;' % (longitude, latitude, distance)


def get_calc_distance(latitude, longitude):
    return 'ST_distance_sphere(point(longitude, latitude), point(%s, %s)) as distance' % (longitude, latitude)


def get_cities(city):
    return 'select distinct(cityName) from HOTELS where cityName like \'%' + city + '%\';'


def check_hotel_exists(hotel_name):
    return 'select id, hotelName from HOTELS where hotelName = \'%s\';' % hotel_name


def check_city_exists(city):
    return 'select distinct(cityName) from HOTELS where cityName = \'%s\';' % city


def get_city_by_hotel(hotel_name):
    return 'select cityName from HOTELS where hotelName = \'%s\';' % hotel_name


def get_address_by_hotel(hotel_name):
    return 'select address from HOTELS where hotelName = \'%s\';' % hotel_name
