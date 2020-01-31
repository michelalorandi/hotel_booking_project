import logging
import mysql.connector
from flask import Flask, render_template
from flask_ask import Ask, request, session, context, question, statement
from datetime import datetime
from num2words import num2words
import queries
import requests

app = Flask(__name__)
ask = Ask(app, "/")
logging.getLogger("flask_ask").setLevel(logging.DEBUG)


def update_dialog_history(session, request, dialog_history_attribute_name='dialog_history'):
    dialog_history = session.attributes.get(dialog_history_attribute_name)

    if dialog_history is None:
        dialog_history = []

    dialog_turn = {"intent": request.get('intent'),
                   "type": request.get("type"),
                   "timestamp": request.get("timestamp")
                   }

    dialog_history.append(dialog_turn)

    session.attributes[dialog_history_attribute_name] = dialog_history
    return dialog_history


def update_dialog_state(session, slots, reset=False, dialog_state_attribute_name='dialog_frame'):
    dialog_state = {}

    if not reset:
        dialog_state = session.attributes.get(dialog_state_attribute_name, {})
        for slot_name, slot_value in slots.items():
            if slot_value is not None:
                dialog_state[slot_name] = slot_value

    session.attributes[dialog_state_attribute_name] = dialog_state

    return dialog_state


def check_conflicts(dialog_state):
    now = datetime.now()
    now = datetime.strptime(str(now.year) + '-' + str(now.month) + '-' + str(now.day), '%Y-%m-%d')
    exception_arr = False
    exception_dep = False
    arrival_date = now
    departure_date = now
    try:
        arrival_date = datetime.strptime(dialog_state.get('arrival_date'), '%Y-%m-%d')
    except ValueError:
        exception_arr = True
        app.logger.info('an exception occur')
    try:
        departure_date = datetime.strptime(dialog_state.get('departure_date'), '%Y-%m-%d')
    except ValueError:
        exception_dep = True
        app.logger.info('an exception occur')

    conflicts = False
    message = ''

    res = execute_db_query(queries.get_city_by_hotel(dialog_state.get('hotel_name')))
    if res is not None and len(res) > 0:
        correct = res[0][0]
        if correct.lower() != dialog_state.get('city').lower():
            conflicts = True
            dialog_state = update_dialog_state(session, {'operation_book': 'conflict_city', 'value': correct})
            message = render_template("utter_ask_conflict_city",
                                      hotel_name=dialog_state.get('hotel_name'),
                                      wrong_city=dialog_state.get('city'),
                                      city=correct)
            return conflicts, message

    if int(dialog_state.get('number_room')) > int(dialog_state.get('number_people')):
        dialog_state = update_dialog_state(session, {'operation_book': 'conflict_room', 'variable': 'number_people'})
        conflicts = True
        message = render_template("utter_ask_conflict_people", number=dialog_state.get('number_people'))
        return conflicts, message

    elif not (exception_arr or exception_dep) and arrival_date == departure_date:
        message = render_template('utter_ask_conflict_equal_dates') + ' ' + render_template('utter_arrival_date')
        dialog_state = update_dialog_state(session, {'variable': 'arrival_date'})
        conflicts = True
        return conflicts, message

    elif not (exception_arr or exception_dep) and arrival_date > departure_date:
        dialog_state = update_dialog_state(session, {'operation_book': 'conflict_dates', 'variable': 'arrival_date'})
        conflicts = True
        message = render_template("utter_ask_conflict_dates",
                                  first_date=dialog_state.get('departure_date'),
                                  second_date=dialog_state.get('arrival_date'))
        return conflicts, message

    elif (not exception_arr) and now > arrival_date:
        dialog_state = update_dialog_state(session, {'operation_book': 'conflict_arrival', 'variable': 'arrival_date'})
        conflicts = True
        message = render_template("utter_ask_conflict_past_arrival_date", date=dialog_state.get('arrival_date'))
        return conflicts, message

    elif (not exception_dep) and now > departure_date:
        dialog_state = update_dialog_state(session, {'operation_book': 'conflict_departure', 'variable': 'departure_date'})
        message = render_template("utter_ask_conflict_past_departure_date", date=dialog_state.get('departure_date'))
        return conflicts, message

    if dialog_state.get('stars') is not None and dialog_state.get('stars') != '':
        hotel_stars = execute_db_query(queries.get_hotel_stars(dialog_state.get('hotel_name')))
        hotel_stars = hotel_stars[0][0]
        if int(hotel_stars) != int(dialog_state.get('stars')):
            conflicts = True
            dialog_state = update_dialog_state(session, {'operation_book': 'conflict_stars', 'value': hotel_stars})
            message = render_template("utter_ask_conflict_stars",
                                      hotel_name=dialog_state.get('hotel_name'),
                                      stars=dialog_state.get('stars'),
                                      correct=hotel_stars)
            return conflicts, message

    if dialog_state.get('address') is not None and dialog_state.get('address') != '':
        res = execute_db_query(queries.get_address_by_hotel(dialog_state.get('hotel_name')))
        app.logger.info(res)
        if res is not None and len(res) > 0:
            correct = res[0][0]
            app.logger.info(correct.lower())
            app.logger.info(dialog_state.get('address').lower())
            if correct.lower() != dialog_state.get('address').lower():
                conflicts = True
                dialog_state = update_dialog_state(session, {'operation_book': 'conflict_address', 'value': correct})
                message = render_template("utter_ask_conflict_address",
                                          hotel_name=dialog_state.get('hotel_name'),
                                          wrong_address=dialog_state.get('address'),
                                          address=correct)
            return conflicts, message
    return conflicts, message


def execute_db_query(query):
    db = mysql.connector.connect(host="localhost",
                                 user="root",
                                 passwd="root",
                                 db="hotelBooking")
    cur = db.cursor()
    cur.execute(query)
    results = []

    for row in cur.fetchall():
        results.append(row)

    db.close()
    return results


def execute_booking(dialog_state):
    if dialog_state.get('hotel_name') is None or dialog_state.get('hotel_name') == '':
        dialog_state = update_dialog_state(session, {"variable": 'hotel_name'})
        message = render_template("utter_ask_hotel_name")
        return message
    else:
        res_check = execute_db_query(queries.check_hotel_exists(dialog_state.get('hotel_name')))
        if len(res_check) < 1:
            dialog_state = update_dialog_state(session, {"operation": "execute_search"})
            message = render_template('utter_not_found_hotels', hotel=dialog_state.get('hotel_name'))
            return message
        elif dialog_state.get('city') is None or dialog_state.get('city') == '':
            res = execute_db_query(queries.get_hotel_city(dialog_state.get('hotel_name')))
            dialog_state = update_dialog_state(session, {"variable": 'city', 'city': res[0][0]})
            message = render_template("utter_ask_city_book", city=res[0][0])
            return message
        elif dialog_state.get('arrival_date') is None or dialog_state.get('arrival_date') == '':
            dialog_state = update_dialog_state(session, {"variable": 'arrival_date'})
            message = render_template("utter_ask_arrival_date")
            return message
        elif dialog_state.get('departure_date') is None or dialog_state.get('departure_date') == '':
            dialog_state = update_dialog_state(session, {"variable": 'departure_date'})
            message = render_template("utter_ask_departure_date")
            return message
        elif dialog_state.get('number_room') is None or dialog_state.get('number_room') == '':
            dialog_state = update_dialog_state(session, {"variable": 'number_room'})
            message = render_template("utter_ask_number_room")
            return message
        elif dialog_state.get('number_people') is None or dialog_state.get('number_people') == '':
            dialog_state = update_dialog_state(session, {"variable": 'number_people'})
            message = render_template("utter_ask_people")
            return message
        else:
            conflicts, message = check_conflicts(dialog_state)

            if conflicts:
                return message
            else:
                if dialog_state.get('stars') is None or dialog_state.get('stars') == '':
                    hotel_stars = execute_db_query(queries.get_hotel_stars(dialog_state.get('hotel_name')))
                    hotel_stars = hotel_stars[0][0]
                else:
                    hotel_stars = dialog_state.get('stars')
                dialog_state = update_dialog_state(session, {"operation": 'booking'})
                room = 'rooms' if int(dialog_state.get('number_room')) > 1 else 'room'
                message = render_template("utter_ask_book",
                                          hotel_name=dialog_state.get('hotel_name'),
                                          stars=hotel_stars,
                                          number_room=dialog_state.get('number_room'),
                                          arrival_date=dialog_state.get('arrival_date'),
                                          departure_date=dialog_state.get('departure_date'),
                                          number_people=dialog_state.get('number_people'),
                                          address=dialog_state.get('address'),
                                          city=dialog_state.get('city'),
                                          room_word=room)
                return message


def execute_search(dialog_state):
    if dialog_state.get('city') is None or dialog_state.get('city') == '':
        dialog_state = update_dialog_state(session, {"variable": 'city'})
        message = render_template("utter_ask_city_search")
        return message
    else:
        res = None
        # The goal of found is to highlight when a city with multiple occurrences is selected
        if not dialog_state.get('found'):
            res = execute_db_query(queries.get_cities(dialog_state.get('city')))
        # if dialog_state.get('found') is not None and (not dialog_state.get('found')):
        # if (not dialog_state.get('found')) and res is not None and len(res) > 1:
        if res is not None and len(res) > 1:
            dialog_state = update_dialog_state(session, {"operation_search": 'select_city'})
            msg = render_template('utter_select_city_1', city=dialog_state.get('city'))
            i = 1
            for r in res:
                msg += ' The ' + num2words(i, ordinal=True) + ' is ' + r[0] + '.'
                i += 1
            msg += ' ' + render_template('utter_select_city_2')
            return msg
        else:
            # ask_found has the goal to skip the question about filters if a question is already activated
            ask_found = False
            qst = ''
            select = ''
            where = ''
            having = ''
            order = ''
            distance = 2000

            if dialog_state.get('address') is not None and dialog_state.get('address') != '':
                URL = "https://nominatim.openstreetmap.org/search?"
                PARAMS = {
                    'q': dialog_state.get('address') + ',' + dialog_state.get('city'),
                    'addressdetails': 1,
                    'format': 'json'
                }
                r = requests.get(url=URL, params=PARAMS)
                res = r.json()
                lat = res[0]['lat']
                lon = res[0]['lon']
                select += ', ' + queries.get_calc_distance(lat, lon)
                having += 'having distance<' + str(distance)
                order += 'distance, '
            elif not ask_found and 1 not in dialog_state.get('skip'):
                ask_found = True
                dialog_state = update_dialog_state(session, {"variable": 'address'})
                qst = render_template('utter_ask_search_address')

            if dialog_state.get('stars') is not None and dialog_state.get('stars') != '':
                where += 'and ' + queries.where_clause_stars(dialog_state.get('stars'))
            elif not ask_found and 2 not in dialog_state.get('skip'):
                ask_found = True
                dialog_state = update_dialog_state(session, {"variable": 'stars'})
                qst = render_template('utter_ask_search_stars')

            if not ask_found:
                dialog_state = update_dialog_state(session, {"operation_search": 'results'})
                qst = render_template('utter_ask_more_results')

            offset = dialog_state.get('page') * 3
            res = execute_db_query(queries.get_hotels_by_city(dialog_state.get('city'), select, where, having, order, offset))
            hotels = []
            app.logger.info(dialog_state.get('clear') is not None and (not dialog_state.get('clear')))
            if dialog_state.get('clear') is not None and (not dialog_state.get('clear')):
                hotels = dialog_state.get('hotels')
            msg = ''
            i = (dialog_state.get('page') * 3) + 1
            for h in res:
                hotels.append({'id': h[0], 'name': h[1]})
                s = 'stars' if h[2] > 1 else 'star'
                msg += 'The ' + num2words(i, ordinal=True) + ' result is ' + h[1] + ' with ' + num2words(h[2]) + ' ' + s + '. '
                i += 1
            if not msg:
                msg = render_template('utter_empty_result')
            else:
                msg += qst
            dialog_state = update_dialog_state(session, {"hotels": hotels, 'found': True, 'clear': False})
            return msg


def execute_do_not_know(dialog_state):
    if dialog_state.get('operation') == 'search':
        if dialog_state.get('operation_search') == 'select_city':
            res = execute_db_query(queries.get_cities(dialog_state.get('city')))
            dialog_state = update_dialog_state(session, {'city': res[0][0]})
            msg = render_template('utter_ask_boh', value=res[0][0])
            msg += ' ' + execute_search(dialog_state)
        elif dialog_state.get('operation_search') == 'results':
            dialog_state = update_dialog_state(session, {"operation_search": 'book'})
            msg = render_template('utter_ask_book_hotel')
        elif dialog_state.get('operation_search') == 'book':
            msg = render_template('utter_restart')
        elif dialog_state.get('variable') == 'city':
            res = execute_db_query(queries.RANDOM_CITY)
            dialog_state = update_dialog_state(session, {'city': res[0][0], 'found': True})
            msg = render_template('utter_ask_boh', value=res[0][0])
            msg += ' ' + execute_search(dialog_state)
        elif dialog_state.get('variable') == 'address':
            skip = dialog_state.get('skip')
            skip.append(1)
            dialog_state = update_dialog_state(session, {"skip": skip, "variable": 'stars'})
            msg = render_template('utter_ask_search_stars')
        elif dialog_state.get('variable') == 'stars':
            skip = dialog_state.get('skip')
            skip.append(2)
            dialog_state = update_dialog_state(session, {"skip": skip, "operation_search": 'results'})
            msg = render_template('utter_ask_more_results')
        else:
            msg = render_template('utter_nevermind')

    elif dialog_state.get('operation') == 'book':
        if dialog_state.get('operation_book') == 'conflict_room':
            dialog_state = update_dialog_state(session, {'number_room': dialog_state.get('number_people'),
                                                         'operation_book': ''})
            msg = execute_booking(dialog_state)
        elif dialog_state.get('operation_book') == 'conflict_dates':
            dialog_state = update_dialog_state(session, {'arrival_date': dialog_state.get('departure_date'),
                                                         'departure_date': dialog_state.get('arrival_date'),
                                                         'operation_book': ''})
            msg = execute_booking(dialog_state)
        elif dialog_state.get('operation_book') == 'conflict_stars':
            dialog_state = update_dialog_state(session, {'stars': dialog_state.get('value'), 'value': '',
                                                         'operation_book': ''})
            msg = execute_booking(dialog_state)
        elif dialog_state.get('operation_book') == 'conflict_city':
            dialog_state = update_dialog_state(session, {'city': dialog_state.get('value'), 'value': '',
                                                         'operation_book': ''})
            msg = execute_booking(dialog_state)
        elif dialog_state.get('operation_book') == 'conflict_address':
            dialog_state = update_dialog_state(session, {'address': dialog_state.get('value'), 'value': '',
                                                         'operation_book': ''})
            msg = execute_booking(dialog_state)
        elif dialog_state.get('variable') == 'arrival_date' or dialog_state.get('variable') == 'departure_date':
            # TODO decidere come proseguire dopo messaggio errore
            msg = render_template('utter_ask_boh_no', variable=dialog_state.get('variable').replace('_', ' '))
        elif dialog_state.get('variable') == 'number_room' or dialog_state.get('variable') == 'number_people':
            dialog_state = update_dialog_state(session, {dialog_state.get('variable'): 1})
            msg = render_template('utter_ask_boh', value=1)
            msg += ' ' + execute_booking(dialog_state)
        elif dialog_state.get('variable') == 'city':
            msg = render_template('utter_ask_boh', value='yes')
            msg += ' ' + execute_booking(dialog_state)
        elif dialog_state.get('variable') == 'hotel_name':
            dialog_state = update_dialog_state(session, {'operation': 'search', 'variable': 'city'})
            msg = render_template('utter_start_search')

    elif dialog_state.get('operation') == 'booking':
        msg = render_template('utter_booked')

    return msg


@ask.launch
def new_booking():
    update_dialog_history(session, request)
    welcome_msg = render_template('welcome')
    dialog_state = update_dialog_state(session, {'repeat': welcome_msg})
    return question(welcome_msg)


@ask.intent("AMAZON.FallbackIntent")
def fallback_intent():
    fall_back_message = "Can you repeat please?"
    update_dialog_history(session, request)
    dialog_state = update_dialog_state(session, {'repeat': fall_back_message})
    return question(fall_back_message)


@ask.intent("AMAZON.StartOverIntent")
def start_over():
    update_dialog_history(session, request)
    dialog_state = update_dialog_state(session, {}, reset=True)
    dialog_state = update_dialog_state(session, {'repeat': render_template('utter_restart')})
    return question(render_template('utter_restart'))


@ask.intent("do_not_know")
def do_not_know():
    update_dialog_history(session, request)
    dialog_state = update_dialog_state(session, {})
    msg = execute_do_not_know(dialog_state)
    dialog_state = update_dialog_state(session, {'repeat': msg})
    return question(msg)


@ask.intent("AMAZON.HelpIntent")
def help_intent():
    update_dialog_history(session, request)
    dialog_state = update_dialog_state(session, {'repeat': render_template('utter_help')})
    # TODO riformula frase help
    return question(render_template('utter_help'))


@ask.intent("AMAZON.RepeatIntent")
def repeat_intent():
    update_dialog_history(session, request)
    dialog_state = update_dialog_state(session, {})
    # TODO riformula frase help
    return question(dialog_state.get('repeat'))


@ask.intent("AMAZON.CancelIntent")
def help_intent():
    update_dialog_history(session, request)
    dialog_state = update_dialog_state(session, {'operation': '',
                                                 'operation_search': '',
                                                 'operation_booking': '',
                                                 'variable': '',
                                                 'value': '',
                                                 'page': 0,
                                                 'hotels': [],
                                                 'repeat': render_template('utter_restart')})
    return question(render_template('utter_restart'))


@ask.intent("AMAZON.PreviousIntent")
def previous_intent():
    update_dialog_history(session, request)
    dialog_state = update_dialog_state(session, {})
    app.logger.error('inside prev')
    if (dialog_state.get('page') > 0) and (dialog_state.get('hotels') is not None):
        app.logger.error('previous')
        page = dialog_state.get('page') - 1
        dialog_state = update_dialog_state(session, {"page": page})
        msg = execute_search(dialog_state)
    else:
        # TODO riscrivere frase
        msg = render_template('utter_no_prev')
    dialog_state = update_dialog_state(session, {'repeat': msg})
    return question(msg)


@ask.intent("AMAZON.NextIntent")
def next_intent():
    update_dialog_history(session, request)
    dialog_state = update_dialog_state(session, {})
    if dialog_state.get('hotels') is not None:
        page = dialog_state.get('page') + 1
        dialog_state = update_dialog_state(session, {"page": page})
        msg = execute_search(dialog_state)
    else:
        # TODO riscrivere frase
        msg = render_template('utter_no_next')
    dialog_state = update_dialog_state(session, {'repeat': msg})
    return question(msg)


@ask.intent("selection",
            {
                'ordinal_number': 'ordinal_number',
                'hotel_name': 'hotel_name'
            }
            )
def select_intent(ordinal_number, hotel_name):
    update_dialog_history(session, request)
    dialog_state = update_dialog_state(session, {})
    hotels = dialog_state.get('hotels')
    if dialog_state.get('operation_search') == 'select_city':
        res = execute_db_query(queries.get_cities(dialog_state.get('city')))
        dialog_state = update_dialog_state(session, {'city': res[int(ordinal_number)-1][0], 'found': True, 'operation_search': ''})
        msg = execute_search(dialog_state)
    elif ordinal_number is not None and hotels is not None and (int(ordinal_number)-1) < len(hotels):
        h_id = hotels[int(ordinal_number)-1]['id']
        res = execute_db_query(queries.get_hotel_by_id(h_id))
        dialog_state = update_dialog_state(session, {"hotel_name": res[0][0],
                                                     "stars": res[0][1],
                                                     "city": res[0][2],
                                                     "address": res[0][3],
                                                     "country": res[0][4],
                                                     "operation": "book"})
        app.logger.info('')
        msg = render_template('utter_current_booking', hotel=res[0][0])
        msg += ' ' + execute_booking(dialog_state)
    elif hotel_name is not None:
        dialog_state = update_dialog_state(session, {'hotel_name': hotel_name, 'operation': 'book'})
        msg = render_template('utter_current_booking', hotel=hotel_name)
        msg += ' ' + execute_booking(dialog_state)
    else:
        dialog_state = update_dialog_state(session, {"operation": "execute_search"})
        msg = render_template('utter_not_found')
    dialog_state = update_dialog_state(session, {'repeat': msg})
    return question(msg)


@ask.intent("search_hotel",
            {
                'number_room': 'number_room',
                'arrival_date': 'arrival_date',
                'departure_date': 'departure_date',
                'stars': 'stars',
                'number_people': 'number_people',
                'address': 'address',
                'city': 'city',
                'country': 'country',
                'region': 'region'
            }
            )
def received_search_hotel(number_room, arrival_date, departure_date, stars, number_people, address, city, country, region):
    update_dialog_history(session, request)
    dialog_history = update_dialog_history(session, request)
    dialog_state = update_dialog_state(session, {"number_room": '',
                                                 "arrival_date": '',
                                                 "departure_date": '',
                                                 "stars": '',
                                                 "number_people": '',
                                                 "address": '',
                                                 "city": '',
                                                 "country": '',
                                                 'region': ''})
    app.logger.info(city)
    found = False
    if city is not None and region is not None:
        city_complete = city + ' (' + region + ')'
        res = execute_db_query(queries.check_city_exists(city_complete))
        app.logger.info(res)
        if res is not None and len(res) > 0:
            city = city_complete
            found = True
    dialog_state = update_dialog_state(session, {"number_room": number_room,
                                                 "arrival_date": arrival_date,
                                                 "departure_date": departure_date,
                                                 "stars": stars,
                                                 "number_people": number_people,
                                                 "address": address,
                                                 "city": city,
                                                 "country": country,
                                                 'region': region,
                                                 "operation": 'search',
                                                 'page': 0,
                                                 'skip': [],
                                                 'hotels': [],
                                                 'found': found,
                                                 'operation_search': '',
                                                 'clear': False})
    msg = execute_search(dialog_state)
    dialog_state = update_dialog_state(session, {'repeat': msg})
    return question(msg)


@ask.intent("book_hotel",
            {
                'hotel_name': 'hotel_name',
                'stars': 'stars',
                'number_room': 'number_room',
                'arrival_date': 'arrival_date',
                'departure_date': 'departure_date',
                'number_people': 'number_people',
                'address': 'address',
                'city': 'city',
                'country': 'country',
                'region': 'region'
            }
            )
def received_book_hotel(hotel_name, stars, number_room, arrival_date, departure_date, number_people, address, city, country, region):
    update_dialog_history(session, request)
    dialog_history = update_dialog_history(session, request)
    dialog_state = update_dialog_state(session, {"hotel_name": '',
                                                 "stars": '',
                                                 "number_room": '',
                                                 "arrival_date": '',
                                                 "departure_date": '',
                                                 "number_people": '',
                                                 "address": '',
                                                 "city": '',
                                                 "country": ''})
    if city is not None and region is not None:
        city_complete = city + ' (' + region + ')'
        res = execute_db_query(queries.check_city_exists(city_complete))
        app.logger.info(res)
        if res is not None and len(res) > 0:
            city = city_complete
    dialog_state = update_dialog_state(session, {"hotel_name": hotel_name,
                                                 "stars": stars,
                                                 "number_room": number_room,
                                                 "arrival_date": arrival_date,
                                                 "departure_date": departure_date,
                                                 "number_people": number_people,
                                                 "address": address,
                                                 "city": city,
                                                 "country": country,
                                                 "operation": 'book',
                                                 "operation_book": '',
                                                 'clear': False})
    msg = execute_booking(dialog_state)
    dialog_state = update_dialog_state(session, {'repeat': msg})
    return question(msg)


@ask.intent("get_information",
            {
                'hotel_name': 'hotel_name',
                'stars': 'stars',
                'number_room': 'number_room',
                'arrival_date': 'arrival_date',
                'departure_date': 'departure_date',
                'number_people': 'number_people',
                'address': 'address',
                'city': 'city',
                'country': 'country',
                'date': 'date',
                'number': 'number',
                'region': 'region'
            }
            )
def received_information(hotel_name, stars, number_room, arrival_date, departure_date, number_people, address, city, country,
                         date, number, region):
    update_dialog_history(session, request)
    dialog_history = update_dialog_history(session, request)
    dialog_state = update_dialog_state(session, {})

    if hotel_name is not None and (dialog_state.get('hotel_name') is None or dialog_state.get('hotel_name') == ''):
        dialog_state = update_dialog_state(session, {'hotel_name': hotel_name})

    if city is not None and (dialog_state.get('city') is None or dialog_state.get('city') == ''):
        dialog_state = update_dialog_state(session, {'city': city})

    if arrival_date is not None and (dialog_state.get('arrival_date') is None or dialog_state.get('arrival_date') == ''):
        dialog_state = update_dialog_state(session, {'arrival_date': arrival_date})

    if departure_date is not None and (dialog_state.get('departure_date') is None or dialog_state.get('departure_date') == ''):
        dialog_state = update_dialog_state(session, {'departure_date': departure_date})

    if number_room is not None and (dialog_state.get('number_room') is None or dialog_state.get('number_room') == ''):
        dialog_state = update_dialog_state(session, {'number_room': number_room})

    if number_people is not None and (dialog_state.get('number_people') is None or dialog_state.get('number_people') == ''):
        dialog_state = update_dialog_state(session, {'number_people': number_people})

    if stars is not None and (dialog_state.get('stars') is None or dialog_state.get('stars') == ''):
        dialog_state = update_dialog_state(session, {"stars": stars})

    if address is not None and (dialog_state.get('address') is None or dialog_state.get('address') == ''):
        dialog_state = update_dialog_state(session, {"address": address})

    if country is not None and (dialog_state.get('country') is None or dialog_state.get('country') == ''):
        dialog_state = update_dialog_state(session, {"country": country})

    if date is not None:
        dialog_state = update_dialog_state(session, {dialog_state.get('variable'): date})

    if number is not None:
        dialog_state = update_dialog_state(session, {dialog_state.get('variable'): number})

    if region is not None and dialog_state.get('region') == '':
        if dialog_state.get('operation_search') == 'select_city':
            c = dialog_state.get('city') + ' (' + region + ')'
            dialog_state = update_dialog_state(session, {'city': c})
        else:
            city_complete = dialog_state.get('city') + ' (' + region + ')'
            res = execute_db_query(queries.check_city_exists(city_complete))
            app.logger.info(city_complete)
            app.logger.info(res)
            if res is not None and len(res) > 0:
                dialog_state = update_dialog_state(session, {'city': city_complete, 'found': True})
            else:
                dialog_state = update_dialog_state(session, {'city': city})

    if dialog_state.get('operation_search') == 'select_city':
        dialog_state = update_dialog_state(session, {'found': True, 'operation_search': ''})

    if dialog_state.get('operation') == 'book':
        msg = execute_booking(dialog_state)
        dialog_state = update_dialog_state(session, {'repeat': msg})
        return question(msg)
    elif dialog_state.get('operation') == 'search':
        dialog_state = update_dialog_state(session, {'clear': True})
        msg = execute_search(dialog_state)
        dialog_state = update_dialog_state(session, {'repeat': msg})
        return question(msg)
    elif dialog_state.get('operation') is None or dialog_state.get('operation') == '':
        dialog_state = update_dialog_state(session, {"operation": 'search',
                                                     'page': 0,
                                                     'skip': [],
                                                     'hotels': [],
                                                     'found': False,
                                                     'clear': False,
                                                     'operation_search': ''})
        msg = execute_search(dialog_state)
        dialog_state = update_dialog_state(session, {'repeat': msg})
        return question(msg)


@ask.intent("greet")
def received_greet():
    update_dialog_history(session, request)
    dialog_state = update_dialog_state(session, {}, reset=True)
    msg = render_template('welcome')
    dialog_state = update_dialog_state(session, {'repeat': msg})
    return question(msg)


@ask.intent("AMAZON.YesIntent")
def received_affirm():
    b = True
    dialog_state = update_dialog_state(session, {})

    if dialog_state.get('operation') == 'new_booking':
        dialog_state = update_dialog_state(session, {}, reset=True)
        msg = render_template('welcome')

    elif dialog_state.get('operation') == 'book':
        if dialog_state.get('operation_book') == 'conflict_room':
            dialog_state = update_dialog_state(session, {'number_room': dialog_state.get('number_people')})
            msg = execute_booking(dialog_state)
        elif dialog_state.get('operation_book') == 'conflict_dates':
            dialog_state = update_dialog_state(session, {'arrival_date': dialog_state.get('departure_date'),
                                                         'departure_date': dialog_state.get('arrival_date')})
            msg = execute_booking(dialog_state)
        elif dialog_state.get('operation_book') == 'conflict_stars':
            msg = execute_do_not_know(dialog_state)
        elif dialog_state.get('operation_book') == 'conflict_city':
            msg = execute_do_not_know(dialog_state)
        elif dialog_state.get('operation_book') == 'conflict_address':
            msg = execute_do_not_know(dialog_state)
        elif dialog_state.get('operation_book') == 'conflict_arrival':
            msg = execute_do_not_know(dialog_state)
        elif dialog_state.get('operation_book') == 'conflict_departure':
            msg = execute_do_not_know(dialog_state)
        elif dialog_state.get('variable') == 'arrival_date':
            msg = render_template('utter_arrival_date')
        elif dialog_state.get('variable') == 'departure_date':
            msg = render_template('utter_departure_date')
        elif dialog_state.get('variable') == 'number_room':
            msg = execute_do_not_know(dialog_state)
        elif dialog_state.get('variable') == 'number_people':
            msg = execute_do_not_know(dialog_state)
        elif dialog_state.get('variable') == 'city':
            msg = execute_booking(dialog_state)
        elif dialog_state.get('variable') == 'hotel_name':
            msg = execute_do_not_know(dialog_state)

    elif dialog_state.get('operation') == 'search':
        if dialog_state.get('operation_search') == 'select_city':
            msg = execute_do_not_know(dialog_state)
        elif dialog_state.get('operation_search') == 'book':
            dialog_state = update_dialog_state(session, {'operation': 'book', 'variable': 'hotel_name'})
            msg = render_template('utter_ask_which_hotel')
        elif dialog_state.get('operation_search') == 'results':
            page = dialog_state.get('page') + 1
            dialog_state = update_dialog_state(session, {"page": page})
            msg = execute_search(dialog_state)
        elif dialog_state.get('variable') == 'stars':
            dialog_state = update_dialog_state(session, {'clear': True})
            msg = render_template('utter_ask_search_affirm_stars')
        elif dialog_state.get('variable') == 'address':
            dialog_state = update_dialog_state(session, {'clear': True})
            msg = render_template('utter_ask_search_affirm_address')
        elif dialog_state.get('variable') == 'city':
            msg = execute_do_not_know(dialog_state)

    elif dialog_state.get('operation') == 'execute_search':
        msg = execute_search(dialog_state)

    else:
        msg = render_template('utter_booked')
        response = statement(msg)
        b = False
        dialog_state = update_dialog_state(session, {}, reset=True)

    if b:
        response = question(msg)
    dialog_state = update_dialog_state(session, {'repeat': msg})
    return response


@ask.intent("AMAZON.NoIntent")
def received_deny():
    dialog_history = update_dialog_history(session, request)
    dialog_state = update_dialog_state(session, {})

    if dialog_state.get('operation') == 'new_booking':
        msg = render_template('utter_goodbye')

    elif dialog_state.get('operation') == 'book':
        if dialog_state.get('operation_book') == 'conflict_room':
            dialog_state = update_dialog_state(session, {'number_people': dialog_state.get('number_room')})
            msg = execute_booking(dialog_state)
        elif dialog_state.get('operation_book') == 'conflict_dates':
            dialog_state = update_dialog_state(session, {'arrival_date': '', 'departure_date': ''})
            msg = execute_booking(dialog_state)
        elif dialog_state.get('operation_book') == 'conflict_arrival':
            msg = execute_do_not_know(dialog_state)
        elif dialog_state.get('operation_book') == 'conflict_departure':
            msg = execute_do_not_know(dialog_state)
        elif dialog_state.get('operation_book') == 'conflict_stars':
            msg = render_template('utter_restart')
        elif dialog_state.get('operation_book') == 'conflict_city':
            msg = render_template('utter_restart')
        elif dialog_state.get('operation_book') == 'conflict_address':
            msg = render_template('utter_restart')
        elif dialog_state.get('variable') == 'city':
            dialog_state = update_dialog_state(session, {"city": ''})
            msg = render_template('utter_ask_city')
        elif dialog_state.get('variable') == 'hotel_name':
            msg = execute_do_not_know(dialog_state)
        elif dialog_state.get('variable') == 'arrival_date':
            msg = execute_do_not_know(dialog_state)
        elif dialog_state.get('variable') == 'departure_date':
            msg = execute_do_not_know(dialog_state)
        elif dialog_state.get('variable') == 'number_room':
            msg = execute_do_not_know(dialog_state)
        elif dialog_state.get('variable') == 'number_people':
            msg = execute_do_not_know(dialog_state)

    elif dialog_state.get('operation') == 'search':
        if dialog_state.get('operation_search') == 'book':
            dialog_state = update_dialog_state(session, {"operation_search": ''})
            msg = render_template('utter_restart')
        elif dialog_state.get('operation_search') == 'select_city':
            msg = execute_do_not_know(dialog_state)
        elif dialog_state.get('operation_search') == 'results':
            dialog_state = update_dialog_state(session, {"operation_search": 'book'})
            msg = render_template('utter_ask_book_hotel')
        elif dialog_state.get('operation_search') == 'book':
            msg = render_template('utter_restart')
        elif dialog_state.get('variable') == 'address':
            msg = execute_do_not_know(dialog_state)
        elif dialog_state.get('variable') == 'city':
            msg = execute_do_not_know(dialog_state)
        elif dialog_state.get('variable') == 'stars':
            msg = execute_do_not_know(dialog_state)

    elif dialog_state.get('operation') == 'execute_search':
        msg = render_template('utter_restart')

    else:
        dialog_state = update_dialog_state(session, {"operation": 'new_booking'})
        msg = render_template('utter_ask_booking')
    dialog_state = update_dialog_state(session, {'repeat': msg})
    return question(msg)


@ask.intent("AMAZON.StopIntent")
def received_stop_intent():
    dialog_state = update_dialog_state(session, {}, reset=True)
    dialog_state = update_dialog_state(session, {'repeat': render_template('utter_goodbye')})
    return statement(render_template('utter_goodbye'))


if __name__ == '__main__':
    app.run(debug=True)
