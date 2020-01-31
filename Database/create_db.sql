create database hotelBooking;

use hotelBooking;

create table HOTELS(
id int NOT NULL AUTO_INCREMENT,
hotelName varchar(255) NOT NULL,
stars int,
price int,
cityName varchar(255),
countryCode varchar(25),
countryName varchar(255),
address varchar(255),
location varchar(255),
url varchar(255),
latitude decimal(10, 8),
longitude decimal(11, 8),
PRIMARY KEY (id)
);

drop table HOTELS;
