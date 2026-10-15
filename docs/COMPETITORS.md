# Rozwiązania pokrewne i miejsce dla HP regen toolkit

Weryfikacja źródeł pierwotnych: **13 października 2026**. To ograniczony przegląd projektów, nie pełny katalog rynku. Otwarty sterownik, serwer druku i otwarty firmware urządzenia to trzy różne rzeczy. Koniec gwarancji nie zmienia licencji istniejącego firmware.

| Projekt | Co faktycznie daje | Czego nie rozwiązuje / warunek | Relacja do toolkit |
| --- | --- | --- | --- |
| [OpenPrinting CUPS](https://github.com/OpenPrinting/cups) | Otwarty system druku na Linux/Unix: kolejki, zarządzanie zadaniami, IPP/AirPrint, lokalne USB i drukarki sieciowe przez Printer Applications lub starsze sterowniki. | Nie zastępuje kodu sterującego silnikami lub głowicą w drukarce; sam nie usuwa jej blokad. | Fundament przyszłego mostu USB → sieć; używać utrzymywanego pakietu dystrybucji, nie przypadkowej gałęzi rozwojowej. |
| [PAPPL / pappl-retrofit](https://github.com/OpenPrinting/pappl-retrofit) | Biblioteka zamieniająca klasyczne sterowniki CUPS/PPD w Printer Applications. Taka aplikacja wystawia starszą drukarkę jako urządzenie IPP, odciążając klientów od instalowania konkretnego sterownika. | Wymaga istniejącego działającego sterownika i właściwego backendu; nie otwiera firmware drukarki. | Integracja i dobór właściwej aplikacji zamiast pisania wszystkich sterowników od zera. |
| [HPLIP](https://developers.hp.com/hp-linux-imaging-and-printing/binary_plugin.html) / [HPLIP Printer Application](https://github.com/OpenPrinting/hplip-printer-app) | Obsługa urządzeń HP; Printer Application opakowuje drukowanie z `hpcups` jako usługę IPP. | Część modeli wymaga zamkniętej wtyczki HP z osobną licencją. Dokumentacja Printer Application wymienia skanowanie jako osobne niezrealizowane zadanie; nie utożsamiać jej możliwości z całym HPLIP. | Baza adapterów dla dokładnie sprawdzonych modeli. UI musi pokazać zależność od zamkniętej wtyczki. |
| [Gutenprint](https://gimp-print.sourceforge.io/) | Otwarte sterowniki wielu drukarek, w tym Canon, Epson i drukarek PCL; przydatne do odzyskiwania obsługi starszego urządzenia. | Zgodność zależy od modelu i funkcji. Projekt ogłosił zakończenie dostarczania nowych binariów macOS; Linux bridge może ograniczyć zależność klienta od takich binariów. | Alternatywny silnik druku; wynik jakości trzeba sprawdzić fizycznie. |
| [ipp-usb](https://github.com/OpenPrinting/ipp-usb) | Proxy HTTP dla **urządzeń obsługujących IPP-over-USB**; udostępnia ich drukowanie IPP, skanowanie eSCL i konsolę WWW, z DNS-SD. | Nie dodaje IPP do każdej starej drukarki USB. Konfiguracja decyduje o wystawieniu usługi lokalnie lub w LAN. | Najkrótsza ścieżka dla zgodnych urządzeń; dla starszych potrzebny sterownik/Printer Application. |
| [PRET — Ruhr University Bochum](https://github.com/RUB-NDS/PRET) | Narzędzie badań bezpieczeństwa drukarek wykorzystujące funkcje języków PostScript, PJL i PCL, przez sieć lub USB. | Nie jest menedżerem bezpiecznych napraw ani uniwersalnym zamiennikiem firmware. Operacje narzędzia mogą mieć skutki dla urządzenia i danych. | Punkt odniesienia dla wiedzy o zagrożeniach; v0.1 nie uruchamia PRET ani jego payloadów. |
| [Open Printer — Open Tools](https://www.opentools.studio/) / [strona zespołu na Crowd Supply](https://www.crowdsupply.com/open-tools/openprinter) | Projekt nowej naprawialnej drukarki; producent opisuje Raspberry Pi Zero W, osobny STM32 do kartridża i użycie CUPS. | To nowa maszyna, nie uniwersalna płyta retrofit HP/Xerox. Producent deklaruje **CC BY-NC-SA 4.0**, zgłoszoną ochronę patentową/wzoru i publikację plików po ukończeniu produktu. | Inspiracja do podziału host/MCU; nie zakładać dostępności kompletnego repo ani prawa do komercyjnego kopiowania. |

Warunek NonCommercial jest wprost opisany w [oficjalnym podsumowaniu CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/). To nie licencja na swobodne komercyjne użycie materiałów. Ewentualne wykorzystanie projektu Open Tools w produkcie wymaga ustalenia osobnych uprawnień; dostępność plików nie jest takim uprawnieniem.

## Co może wyróżnić produkt

Wspólna aplikacja prowadzi użytkownika od wykrycia urządzenia do **konkretnej, zweryfikowanej ścieżki przywrócenia użyteczności**: urządzenie IPP → odpowiedni sterownik → most USB/LAN → naprawa konkretnego modelu. Pokazuje dowody zgodności, kopie konfiguracji i plan powrotu. Rozróżnia „drukuje przez otwarty host”, „wymaga zamkniętej wtyczki” i „ma otwarty kontroler”.

W sprawdzonych źródłach nie znaleziono potwierdzenia uniwersalnego, bezpiecznego zamiennika firmware HP/Xerox ani uniwersalnego jailbreaku. Ten wynik nie dowodzi, że żaden projekt lub modelowa metoda nie istnieje. Przed wdrożeniem konieczne jest sprawdzenie dokładnego modelu, rewizji płyty i wersji firmware.

## Zakres działającej v0.1

Lokalne wykrywanie IPP/IPPS i inspekcja tylko po wyborze zakresu przez użytkownika, raport oraz offline preflight pliku firmware. Dostępna jest też lista lokalnych kolejek CUPS, plan konfiguracji i utworzenie nowej kolejki driverless po jawnym potwierdzeniu użytkownika, na macOS/Linux z dostępnym CUPS i odpowiednimi uprawnieniami. Wymaga to drukarki zgodnej z IPP Everywhere lub już działającego zgodnego mostu IPP; wynik konfiguracji nie zastępuje fizycznego wydruku testowego. Preflight bada zgodność deklaracji, rozmiar i SHA-256; **nie potwierdza autentyczności, bezpieczeństwa ani możliwości odzyskania urządzenia**. Pełny most USB, instalacja sterowników, aktualizacje firmware i kontrolery sprzętowe pozostają roadmapą. Żaden model nie uzyskuje statusu „flash supported” na podstawie samego katalogu lub nazwy znalezionej w sieci.

## Otwarte kwestie

- Dokładny pierwszy model HP/Xerox, kod produktu, rewizja płyty i aktualny firmware.
- Co przestało działać: Wi-Fi, brak sterownika, boot, blokada materiałów, mechanika czy usługa producenta.
- Czy urządzenie działa przez USB/Ethernet i drukuje lokalną stronę diagnostyczną.
- OS pierwszych użytkowników, dostęp do sprzętu laboratoryjnego i legalne źródła plików.

Źródła techniczne dodatkowo: [podręcznik Printer Applications](https://openprinting.github.io/documentation/05-User-Manual), [lista sterowników i aplikacji OpenPrinting](https://openprinting.github.io/cups/drivers.html). Listy zgodności są punktem wyjścia, nie dowodem testu w tym projekcie.
