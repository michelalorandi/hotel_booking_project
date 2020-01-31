# Hotel booking skill
Second project for the 2018/2019 Language Understanding Systems course @ UniTn 
## Requirements 
In order to properly execute the program, you must have installed the python libraries in the `requirements.txt` file in the root of the repository. 
## Hotel booking skill 
In order to start the execution of the server, you need to run the command `python hotel_booking_app.py`
The server runs on the port 5000 and can be tested using ngrok (https://ngrok.com/download). 
### Database 
The database can be created using the sql script `./Database/create_db.sql` 
After the creation of the database, we can populate it using the sql script `./Database/populate_db.sql`
### Intents 
The utterances used for the training of the skill are in the `./Intents` folder. Each file contains the utterances of the respective intent. For example, the `./Intents/utterances_search.txt` file contains the utterances of the search intent. 
### Report 
In the `./Report` folder, the project report and the video presentation can be found. 
