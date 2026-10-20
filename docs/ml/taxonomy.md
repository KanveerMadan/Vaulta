# Category taxonomy

Source of truth: `backend/app/data/taxonomy.json` (the web app reads a copy, `frontend/src/lib/taxonomy.json`;
`tests/test_taxonomy.py` keeps them identical). Loaded by `backend/app/services/taxonomy.py`.

## Shape

- **Groups (20, plus 4 set by the system).** A transaction's `category` is always a group. The groups keep the
  names categories had before the taxonomy, so no stored transaction, budget, rule or goal changed value. New groups:
  Personal Care, Gifts & Donations and Income.
- **Subcategories (130).** `subcategory` is optional and always inside its group. It is a taxonomy id
  (`food.delivery`) or one of the user's own (`custom:<uuid>`, Settings → Categories). The merchant model
  (`docs/MODEL_CARD.md`) predicts a subcategory; the group is derived from it, never predicted separately.
- **System groups** are never predicted: Sent to People and Received from People (set from the payment's nature),
  Misc cash (the weekly cash count), and Other (the user's own choice).
- **Tags** are separate from categories: many-to-many labels ("Goa trip", "Reimbursable") with their own filter
  on the transactions page, totals in reports (`spend_summary(group_by="tag")`) and in chat (`search_transactions`
  with `tag`, `spend_summary` grouped by tag). A transaction with two tags counts under both, so tag totals can add up
  to more than total spending; the reports say so.

## Edits, rules and budgets

- **Edits.** Choosing a subcategory sets its group. Choosing a group keeps the subcategory only if it is in that group.
  A user edit locks category and subcategory together: detection, rules and the model never change either again.
- **Rules.** Two consistent subcategory edits for a merchant make a rule whose value is the subcategory; a rule's
  value can be a group or a subcategory.
- **Budgets.** A budget is either on a group (as before) or on one subcategory of a group. A subcategory budget sits
  inside its group's budget, not on top of it (the total of category limits leaves it out). It raises the same 80% and
  100% alerts.

## Migration (`alembic/versions/f5a1b3c7d9e2_taxonomy_tags.py`)

- Adds `transactions.subcategory` and `transactions.auto_subcategory`, plus `budgets.subcategory` (the one-active-budget
  index now includes it).
- Adds the `custom_subcategories`, `tags` and `transaction_tags` tables, each with row-level security. Their names are
  encrypted (`Searchable`), so they stay unique per user.
- Existing values are untouched, because the groups are the old category names.
- Existing rows get subcategories from the re-categorisation job (`backend/scripts/recategorise.py`,
  [DEPLOY.md](../DEPLOY.md#your-machine-migrations-and-key-rotation-never-on-render-or-vercel)). It has a dry run, can be undone and never changes a row the user corrected. That includes
  Policybazaar, which moved from Finance to Insurance.

## Edge cases (how a merchant is labelled when the narration can't tell)

The narration is all anyone sees (not the basket or the bill), so labels follow what the merchant mostly is:

| Merchant / case | Subcategory | Why |
|---|---|---|
| Blinkit, Zepto, Swiggy Instamart, BB Now, Flipkart Minutes | Groceries › Quick commerce | Mostly groceries; the basket isn't visible. |
| BigBasket, JioMart, Amazon Fresh | Groceries › Online grocery | Scheduled grocery delivery. |
| Swiggy, Zomato | Food & Dining › Food delivery | "Swiggy Instamart" / "Instamart" in the narration is Quick commerce instead. |
| Amazon, Flipkart, Meesho | Shopping › Online marketplaces | The item isn't visible. Amazon Prime is Video streaming, Amazon Pay bill payments are Utilities › Bill payment services, Amazon Pay Later is Finance › Pay later. |
| Apollo Pharmacy, MedPlus, Tata 1mg, PharmEasy, Netmeds, local "medicals" | Health › Pharmacy | Apollo *Hospitals* is Health › Hospitals. |
| Indian Oil, HPCL, BPCL, Shell, Nayara (also a card POS at a pump) | Transport › Fuel | |
| FASTag recharges and tolls | Transport › Tolls & FASTag | |
| Credit card bill payments (CRED card payment, BillDesk card payment, "CC PAYMENT") | Transfers › Credit card bills | Not spending: the card's own statement has the purchases. Detection already treats these as transfers. |
| CRED with no sign of a card bill, Google Pay, PhonePe, Paytm with the merchant hidden | Finance › Payment apps | |
| Rent through NoBroker, CRED Rent, RentPay, Housing.com | Rent & Housing › Rent | |
| Rent paid to a person (UPI to an individual) | not labelled by the model | Personal payments are masked and handled by the person's tag ("Rent"): the model only ever sees merchant strings. |
| Society maintenance (MyGate, NoBrokerHood, ADDA) | Rent & Housing › Society maintenance | |
| MakeMyTrip, Goibibo, Cleartrip, Yatra | Travel › Travel booking sites | The booking type isn't visible. |
| IRCTC | Travel › Trains | City metro and suburban trains are Transport › Metro, bus & local train. |
| Airtel, Jio, Vi, BSNL | Utilities › Mobile recharge & bills | Their broadband and DTH narrations ("AIRTEL XSTREAM FIBER", "AIRTEL DTH") belong in Broadband and DTH; the rule-based normalizer can't tell them apart and says Mobile. |
| Salaries, interest, cashback, dividends | Income › … | Income subcategories are used for credits only. |
| ATM withdrawals | Cash › ATM withdrawals | The cash wallet then tracks it. |
| Dream11, MPL, rummy and poker apps | Entertainment › Fantasy sports & real-money games | |
| Nykaa, Purplle | Shopping › Beauty & cosmetics | Salons are Personal Care › Salons & barbers. |
| Lenskart, Titan Eye+ | Shopping › Eyewear | Eye check-ups are Health › Eye care. |

## Groups and subcategories

### Food & Dining

| Subcategory | Id | Definition |
|---|---|---|
| Food delivery | `food.delivery` | Restaurant food ordered through a delivery app (Swiggy, Zomato, EatSure). |
| Restaurants | `food.restaurant` | Sit-down restaurants, dhabas and family dining, paid at the venue. |
| Fast food | `food.fast_food` | Quick-service chains and outlets (McDonald's, Domino's, KFC, Subway), at the outlet or on their own app. |
| Cafes & coffee | `food.cafe` | Coffee shops, tea chains and cafes (Starbucks, Chaayos, Third Wave). |
| Bars & pubs | `food.bar` | Pubs, bars, breweries, lounges and liquor shops. |
| Bakeries & sweets | `food.bakery_sweets` | Bakeries, cake shops, mithai and sweet shops, ice cream parlours. |
| Street food & snacks | `food.street_food` | Chaat, juice, tea stalls, small snack counters and food carts. |
| Canteens & mess | `food.canteen` | Office or college canteens, messes, tiffin and meal subscription services. |
| Catering | `food.catering` | Caterers and bulk food orders for events. |

### Groceries

| Subcategory | Id | Definition |
|---|---|---|
| Quick commerce | `groceries.quick_commerce` | 10–30 minute delivery apps (Blinkit, Zepto, Swiggy Instamart, BB Now, Flipkart Minutes). Counted as groceries even when the basket had other things: the narration can't show the basket. |
| Online grocery | `groceries.online` | Scheduled online grocery delivery (BigBasket, JioMart, Amazon Fresh). |
| Supermarkets | `groceries.supermarket` | Supermarket and hypermarket chains (DMart, More, Reliance Fresh, Spencer's, Star Bazaar). |
| Kirana & general stores | `groceries.kirana` | Neighbourhood kirana, provision and general stores. |
| Fruits & vegetables | `groceries.fruits_vegetables` | Fruit and vegetable vendors and chains (FreshToHome produce, Kisan Konnect, local sabzi shops). |
| Milk & dairy | `groceries.dairy` | Milk subscriptions and dairies (Country Delight, Milkbasket, Amul parlours, local dairy). |
| Meat & fish | `groceries.meat_fish` | Butchers, fish and meat shops and apps (Licious, FreshToHome). |
| Gourmet & organic | `groceries.specialty` | Gourmet, organic and imported food stores (Nature's Basket, Foodhall, organic stores). |

### Shopping

| Subcategory | Id | Definition |
|---|---|---|
| Online marketplaces | `shopping.marketplace` | General online marketplaces where the item isn't visible (Amazon, Flipkart, Meesho, Snapdeal). Amazon Pay bill payments, Amazon Prime and Amazon Fresh go to their own subcategories. |
| Clothing & fashion | `shopping.fashion` | Clothing stores and fashion apps (Myntra, Ajio, Zudio, Westside, Max, local garment shops). |
| Footwear | `shopping.footwear` | Shoe stores and brands (Bata, Metro Shoes, Puma, Nike stores). |
| Electronics & appliances | `shopping.electronics` | Phones, computers, appliances and their accessories (Croma, Reliance Digital, Vijay Sales, Apple, local mobile shops). |
| Home & furniture | `shopping.home_furniture` | Furniture, furnishing, kitchenware and decor (IKEA, Pepperfry, Urban Ladder, Home Centre). |
| Hardware & home improvement | `shopping.hardware` | Hardware, paint, plumbing, electrical and building-material shops. |
| Beauty & cosmetics | `shopping.beauty` | Cosmetics, skincare and fragrance stores and apps (Nykaa, Purplle, Sugar, The Body Shop). Salons are Personal Care. |
| Books & stationery | `shopping.books_stationery` | Bookshops, stationery and office supplies (Crossword, Sapna, local stationers). |
| Kids & toys | `shopping.kids` | Baby products, kids' clothing and toys (FirstCry, Hamleys). |
| Sports & outdoor | `shopping.sports` | Sports goods, cycles and outdoor gear (Decathlon). |
| Jewellery | `shopping.jewellery` | Jewellers and jewellery brands (Tanishq, Kalyan, CaratLane, local jewellers). |
| Eyewear | `shopping.eyewear` | Spectacles and sunglasses stores (Lenskart, Titan Eye+). Eye check-ups are Health. |
| Watches, bags & accessories | `shopping.watches_accessories` | Watches, bags, luggage and fashion accessories (Titan, Fastrack, VIP, Safari). |
| Gifts & flowers | `shopping.gifts_flowers` | Gift shops, florists, gift cards and gifting sites (Ferns N Petals, IGP, Archies). |
| Pet supplies | `shopping.pets` | Pet food and supplies (Supertails, Heads Up For Tails). Vets are Health. |
| Department stores | `shopping.department_store` | Multi-category department stores and malls (Shoppers Stop, Lifestyle, Pantaloons, Central). |
| Paan & tobacco | `shopping.paan_tobacco` | Paan shops and tobacco or cigarette sellers. |

### Transport

| Subcategory | Id | Definition |
|---|---|---|
| Cabs | `transport.ride_hailing` | Cab rides booked in an app (Uber, Ola, BluSmart, Meru). |
| Bike taxis & autos | `transport.bike_auto` | Bike taxis and auto-rickshaws (Rapido, Namma Yatri, auto drivers paid by UPI QR). |
| Fuel | `transport.fuel` | Petrol pumps and fuel (Indian Oil, HPCL, BPCL, Shell, Nayara), also when paid by card at a POS. |
| EV charging | `transport.ev_charging` | Electric vehicle charging (Tata Power EZ Charge, Statiq, ChargeZone). |
| Metro, bus & local train | `transport.public_transit` | City public transport: metro cards and tickets, city buses, suburban trains. |
| Parking | `transport.parking` | Parking fees and parking apps. |
| Tolls & FASTag | `transport.tolls` | Highway tolls and FASTag recharges. |
| Vehicle service & parts | `transport.vehicle_service` | Car and bike servicing, repairs, tyres, washing, spare parts and accessories (GoMechanic, authorised service centres). |
| Vehicle rental | `transport.vehicle_rental` | Self-drive cars, bikes and scooters by the hour or day (Zoomcar, Yulu, Bounce, Royal Brothers). |

### Travel

| Subcategory | Id | Definition |
|---|---|---|
| Flights | `travel.flights` | Airline tickets bought from the airline (IndiGo, Air India, Akasa Air, SpiceJet). |
| Trains | `travel.trains` | Long-distance train tickets (IRCTC). City metro and local trains are Transport. |
| Intercity buses | `travel.bus` | Intercity bus tickets (redBus, AbhiBus, state transport corporations). |
| Hotels & stays | `travel.hotels` | Hotels, homestays and hostels (OYO, Taj, Treebo, Zostel, Airbnb). |
| Travel booking sites | `travel.booking` | Online travel agencies where the booking type isn't visible (MakeMyTrip, Goibibo, Cleartrip, Yatra, EaseMyTrip). |
| Holidays & tours | `travel.holidays` | Tour operators, holiday packages and travel experiences (Thomas Cook, SOTC, Thrillophilia). |
| Forex, visa & passport services | `travel.forex_visa` | Currency exchange, forex cards, visa processing (VFS Global, BookMyForex). Government passport fees are Taxes & Government. |

### Utilities

| Subcategory | Id | Definition |
|---|---|---|
| Electricity | `utilities.electricity` | Electricity boards and distribution companies (BESCOM, MSEDCL, Tata Power, Adani Electricity, TNEB). |
| Water | `utilities.water` | Municipal water bills, water tankers and drinking-water can delivery. |
| Piped gas | `utilities.piped_gas` | Piped natural gas (Mahanagar Gas, IGL, Gujarat Gas). |
| LPG cylinders | `utilities.lpg` | LPG cylinder bookings (Indane, HP Gas, Bharat Gas). |
| Mobile recharge & bills | `utilities.mobile` | Prepaid recharges and postpaid bills (Jio, Airtel, Vi, BSNL). |
| Broadband & internet | `utilities.broadband` | Home broadband and fibre (ACT Fibernet, Hathway, JioFiber, Airtel Xstream Fiber, Excitel). |
| DTH & cable TV | `utilities.dth_cable` | Satellite and cable TV (Tata Play, Dish TV, Airtel Digital TV, Sun Direct, local cable operators). |
| Bill payment services | `utilities.bill_payments` | Bill-payment services where the biller isn't visible (BillDesk, BBPS, Amazon Pay bills, Paytm bill payments). |

### Rent & Housing

| Subcategory | Id | Definition |
|---|---|---|
| Rent | `housing.rent` | Rent paid through a rent platform or to a company landlord (NoBroker, CRED Rent, RentPay, Housing.com Pay Rent). Rent paid to a person is handled by the person's tag: the model never sees personal payments. |
| Society maintenance | `housing.society_maintenance` | Housing society maintenance and apartment management apps (MyGate, NoBrokerHood, ADDA). |
| Home services | `housing.home_services` | Booked home services: cleaning, pest control, appliance repair, salon at home (Urban Company, Housejoy). |
| Repairs & renovation | `housing.repairs` | Plumbers, electricians, carpenters, interior work and renovation (Livspace). |
| Domestic help | `housing.domestic_help` | Agencies for maids, cooks, drivers and nannies. |
| Packers & movers | `housing.movers` | Moving and relocation services. |
| Property sites & brokerage | `housing.property` | Property portals, brokers and deposits through them (99acres, Magicbricks, Housing.com, Square Yards). |

### Health

| Subcategory | Id | Definition |
|---|---|---|
| Pharmacy | `health.pharmacy` | Chemists and online pharmacies (Apollo Pharmacy, MedPlus, Tata 1mg, PharmEasy, Netmeds, local medical stores). |
| Doctors & consultations | `health.doctor` | Clinics, doctors' fees and online consultations (Practo, Lybrate, MFine). |
| Hospitals | `health.hospital` | Hospital bills (Apollo Hospitals, Fortis, Manipal, Max, AIIMS). Apollo Pharmacy is Pharmacy. |
| Lab tests & diagnostics | `health.diagnostics` | Labs, scans and health check-ups (Dr Lal PathLabs, Thyrocare, Metropolis, Redcliffe, Healthians). |
| Dental | `health.dental` | Dentists and dental clinics (Clove Dental). |
| Eye care | `health.eye_care` | Eye hospitals and check-ups (Dr Agarwal's, Vasan). Spectacles shops are Shopping. |
| Fitness & wellness | `health.fitness` | Gyms, yoga, fitness and wellness apps (Cult.fit, Gold's Gym, Anytime Fitness, HealthifyMe). |
| Home healthcare & vets | `health.home_care` | Nursing at home, physiotherapy, elder care and veterinary clinics (Portea). |

### Personal Care

| Subcategory | Id | Definition |
|---|---|---|
| Salons & barbers | `personal_care.salon` | Hair salons and barbers (Naturals Salon, Lakme Salon, Green Trends, local barbers). |
| Spa & massage | `personal_care.spa` | Spas, massage and beauty parlours. |
| Laundry & dry cleaning | `personal_care.laundry` | Laundry, ironing and dry cleaning (UClean, Tumbledry, local dhobi). |
| Tailoring | `personal_care.tailoring` | Tailors and alterations. |

### Entertainment

| Subcategory | Id | Definition |
|---|---|---|
| Video streaming | `entertainment.video_streaming` | Video subscriptions (Netflix, Prime Video, JioHotstar, SonyLIV, ZEE5, YouTube Premium). |
| Music & audio | `entertainment.music_streaming` | Music, podcast and audiobook subscriptions (Spotify, JioSaavn, Gaana, Wynk, Audible, Pocket FM). |
| Movies | `entertainment.movies` | Cinema tickets and multiplexes (PVR INOX, Cinepolis, BookMyShow movie tickets). |
| Events & live shows | `entertainment.events` | Concerts, plays, sports matches and event tickets (District, Insider, BookMyShow events). |
| Gaming | `entertainment.gaming` | Video games, in-game purchases and game stores (Steam, PlayStation Store, Google Play games). |
| Fantasy sports & real-money games | `entertainment.fantasy_sports` | Fantasy sports, rummy, poker and other real-money gaming (Dream11, MPL, My11Circle, Rummy Circle). |
| Amusement & outings | `entertainment.amusement` | Amusement and water parks, gaming zones, bowling, zoos and museums (Wonderla, Imagica, Smaaash). |
| Hobbies & clubs | `entertainment.hobbies` | Clubs, hobby classes and memberships (sports clubs, art and music classes for adults). |

### Education

| Subcategory | Id | Definition |
|---|---|---|
| School fees | `education.school` | School fees and school-related payments. |
| College & university | `education.college` | College and university fees. |
| Online courses | `education.online_learning` | Online learning platforms and courses (Coursera, Udemy, Unacademy, upGrad, Scaler). |
| Coaching & tuition | `education.coaching` | Coaching institutes and tuition (Allen, Aakash, FIITJEE, BYJU'S, Vedantu, PhysicsWallah). |
| Exam & application fees | `education.exams` | Entrance and certification exam fees (NTA, GMAC, ETS, university application fees). |
| Daycare & preschool | `education.childcare` | Creches, daycare and preschools (Kidzee, EuroKids, Klay). |

### Software & Cloud

| Subcategory | Id | Definition |
|---|---|---|
| Cloud & hosting | `software.cloud` | Cloud computing and hosting (AWS, Google Cloud, Azure, DigitalOcean, Vercel). |
| Developer tools | `software.dev_tools` | Developer services (GitHub, Atlassian, JetBrains, OpenAI API). |
| Productivity & work apps | `software.productivity` | Work software (Notion, Slack, Zoom, Microsoft 365, Google Workspace, Figma, Canva, Adobe). |
| Cloud storage & app stores | `software.storage` | Personal storage and app store subscriptions (Google One, iCloud, Apple services, Google Play apps). |
| Domains & websites | `software.domains` | Domains and website builders (GoDaddy, Hostinger, Namecheap, Wix). |
| AI tools | `software.ai_tools` | AI assistant subscriptions (ChatGPT, Claude, Perplexity, Midjourney). |

### Finance

| Subcategory | Id | Definition |
|---|---|---|
| Payment apps | `finance.payment_app` | Payments through a payment app or wallet where the actual merchant isn't visible (Google Pay, PhonePe, Paytm, CRED, MobiKwik). |
| Loan EMIs | `finance.loan_emi` | Loan and EMI repayments (home, car, personal, consumer durable loans: Bajaj Finserv, HDFC loan EMI, NACH debits to lenders). |
| Pay later | `finance.bnpl` | Buy-now-pay-later repayments (Simpl, LazyPay, Amazon Pay Later, Slice). |
| Bank charges & fees | `finance.bank_charges` | Bank charges, card annual fees, late fees, interest charged, SMS and ATM fees. |
| Money transfer services | `finance.remittance` | International money transfer services (Wise, Western Union, Remitly). |

### Insurance

| Subcategory | Id | Definition |
|---|---|---|
| Health insurance | `insurance.health` | Health insurance premiums (Star Health, Niva Bupa, Care Health, HDFC Ergo health). |
| Life insurance | `insurance.life` | Life and term insurance premiums (LIC, HDFC Life, SBI Life, ICICI Prudential, Max Life). |
| Motor insurance | `insurance.motor` | Car and bike insurance (Acko, Digit, Bajaj Allianz motor). |
| Other insurance | `insurance.general` | General insurers where the policy type isn't visible, plus travel, home and gadget insurance (Bajaj Allianz, ICICI Lombard, Tata AIG). |
| Insurance platforms | `insurance.platform` | Insurance comparison and broking platforms (Policybazaar, InsuranceDekho, Turtlemint). |

### Investments

| Subcategory | Id | Definition |
|---|---|---|
| Mutual funds & SIPs | `investments.mutual_funds` | Mutual fund purchases and SIPs (Groww, Zerodha Coin, Kuvera, AMC collections via BSE StAR MF / CAMS / KFintech). |
| Stocks & brokers | `investments.stocks` | Money added to stock brokers (Zerodha, Upstox, Angel One, ICICI Direct, Dhan). |
| Fixed & recurring deposits | `investments.deposits` | FDs and RDs opened from the account. |
| Gold & silver | `investments.gold` | Digital gold, sovereign gold bonds and bullion (SafeGold, MMTC-PAMP, Augmont). |
| PPF, NPS & retirement | `investments.retirement` | PPF, NPS, EPF voluntary contributions and Sukanya Samriddhi. |
| Crypto | `investments.crypto` | Crypto exchanges (CoinDCX, WazirX, CoinSwitch, Mudrex). |

### Taxes & Government

| Subcategory | Id | Definition |
|---|---|---|
| Income tax | `taxes.income_tax` | Income tax, advance tax and TDS payments (e-Pay Tax, TIN-NSDL). |
| GST | `taxes.gst` | GST payments. |
| Property & municipal tax | `taxes.property_tax` | Property tax and municipal corporation payments (BBMP, MCGM, GHMC). |
| Government fees | `taxes.government_fees` | Passport, RTO, stamp duty, registration and other government service fees (Passport Seva, Parivahan, MCA). |
| Fines & challans | `taxes.fines` | Traffic challans and other penalties. |

### Gifts & Donations

| Subcategory | Id | Definition |
|---|---|---|
| Charity & NGOs | `donations.charity` | Donations to charities and NGOs (GiveIndia, CRY, Akshaya Patra). |
| Religious donations | `donations.religious` | Temples, gurudwaras, churches, mosques and religious trusts (TTD, Shirdi Sai Baba Sansthan). |
| Crowdfunding | `donations.crowdfunding` | Crowdfunding campaigns (Ketto, Milaap, ImpactGuru). |

### Income (credits only)

| Subcategory | Id | Definition |
|---|---|---|
| Salary | `income.salary` | Salary and wages from an employer. |
| Interest | `income.interest` | Interest credited on savings accounts and deposits. |
| Dividends | `income.dividends` | Dividends from shares and mutual funds. |
| Cashback & rewards | `income.cashback` | Cashback, rewards and referral bonuses credited. |
| Business & freelance | `income.business` | Payments from clients and payment-gateway settlements for the user's own business. |
| Refunds from government | `income.government` | Income tax refunds, subsidies (LPG DBT) and other government credits. |

### Transfers

| Subcategory | Id | Definition |
|---|---|---|
| Own-account transfers | `transfers.own_account` | Money moved between the user's own accounts or wallets. |
| Credit card bills | `transfers.credit_card_bill` | Paying a credit card bill (CRED card payment, BillDesk card payment, "CC payment"). Not spending: the card's own statement has the purchases. |

### Cash

| Subcategory | Id | Definition |
|---|---|---|
| ATM withdrawals | `cash.atm` | Cash withdrawn at an ATM or a bank branch. |
