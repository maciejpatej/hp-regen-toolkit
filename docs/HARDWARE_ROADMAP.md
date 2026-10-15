# Od mostu druku do otwartego kontrolera

To plan inżynierski, nie instrukcja przerabiania zasilacza ani deklaracja zgodności istniejącego sprzętu. Na dziś toolkit **nie steruje mechaniką i nie zapisuje firmware drukarki**. Pierwszy etap ma działać z zachowaniem fabrycznej elektroniki.

## Etap 1 — odwracalny most USB / Ethernet → LAN

Raspberry Pi lub mały komputer Linux podłącza się do sprawnej drukarki przez USB/Ethernet, a użytkownicy drukują przez IPP. Host przejmuje kolejkę, rasteryzację i wygodny interfejs; toolkit dobiera zweryfikowaną ścieżkę i zbiera diagnostykę. Fabryczny kontroler nadal obsługuje mechanikę i zabezpieczenia.

- Dla urządzenia IPP-over-USB sprawdzić `ipp-usb`; dla starszego USB wybrać właściwy sterownik i Printer Application.
- Instalować utrzymywane, przypięte wersje pakietów i zapisywać ich wersje w raporcie. Nie wystawiać panelu administracyjnego bezpośrednio do Internetu.
- Przechowywać poprzednią konfigurację kolejki. Testować podłączenie, druk, anulowanie, restart hosta i drukarki oraz ponowne wykrycie.
- Pierwszy pilot: jeden fizyczny model, jeden OS hosta, jedna wersja sterownika. Dopiero potem kolejne modele.

Ten most może ominąć wadliwą ścieżkę Wi-Fi przez użycie sprawnego USB, ale **nie naprawia firmware, niesprawnej mechaniki ani blokady wewnątrz urządzenia**. CUPS obsługuje lokalne/sieciowe drukarki i otwarte aplikacje druku; `ipp-usb` wymaga IPP-over-USB. [CUPS](https://github.com/OpenPrinting/cups), [ipp-usb](https://github.com/OpenPrinting/ipp-usb).

**Gate:** 10 kolejnych reprezentatywnych zadań na egzemplarzu, anulowanie i wznowienie bez zawieszenia, 3 cykle restartu, akceptacja jakości wydruku przez człowieka, raport z wersjami i nieujawniającymi dokumentów logami. To proponowany gate projektu, nie obietnica producentów komponentów.

## Etap 2 — modelowy pakiet naprawczy

Najpierw identyfikacja dokładnego wariantu i usterki. Adapter opisuje wspierane odczyty, kopię ustawień, legalne źródło aktualizacji oraz przetestowany recovery. Każda operacja zapisu ma osobny przegląd i osobny gate z [MODEL_ADAPTERS.md](MODEL_ADAPTERS.md). Rozpoznanie rodziny „LaserJet” albo podobnego VID/PID nie wystarcza do włączenia aktualizacji.

**Gate:** pełna tożsamość modelu/rewizji, jawna lista wersji firmware, pochodzenie obrazu, zgodność rozmiaru/hash, potwierdzone odzyskanie na urządzeniu laboratoryjnym i ręczne zatwierdzenie testu. Brak któregoś dowodu oznacza status eksperymentalny i zablokowany zapis.

## Etap 3 — pomiar i prototyp własnego kontrolera

„Arduino zamiast elektroniki HP” wymaga projektu dla **konkretnego mechanizmu**. Sama marka płytki nie określa możliwości. Trzeba poznać sterowanie głowicą, enkoderem, silnikami, czujnikami papieru i procedurami czyszczenia; oszacować przepustowość danych, wymagane czasy, pamięć i układy zasilania. Nie można obiecać uniwersalnego szkicu Arduino.

| Warstwa | Zadania | Wymagane dowody |
| --- | --- | --- |
| Host Linux / Raspberry Pi | UI, IPP, kolejka, rendering dokumentów i przygotowanie rastra; izolacja od sieci i aktualizacje hosta. | Obsługiwane formaty, czas rasteryzacji, pamięć dla największej strony, kontrola przepływu i obsługa restartu. |
| MCU czasu rzeczywistego; ewentualnie FPGA/układ dedykowany po pomiarach | Ruch, odczyt enkodera i czujników, deterministyczna synchronizacja głowicy, watchdog i zatrzymanie awaryjne. | Limity czasowe, poziomy elektryczne, prąd, bezpieczny stan po zaniku łącza/zasilania. |
| Fabryczne lub zweryfikowane układy bezpieczeństwa | Interlocki, odcięcie energii, ochrona termiczna i mechaniczna. | Fizyczne testy zabezpieczeń wykonane przez kompetentnego człowieka; niezależność od zawieszenia aplikacji. |

Podział host + MCU jest decyzją projektową do sprawdzenia, nie dowodem wykonalności retrofit HP. Jako przykład innej konstrukcji, Open Tools opisuje [Pi Zero W + STM32 w Open Printer](https://www.crowdsupply.com/open-tools/openprinter). Nie kopiować ich materiałów do projektu komercyjnego bez odpowiednich uprawnień.

### Granice prototypu

- Zacząć od niskiego ryzyka: osobny mechanizm stanowiskowy, ograniczona energia, oryginalne interlocki i nadzór. Nie wykonywać zmian w sieciowym zasilaniu, grzałkach utrwalacza, torze wysokiego napięcia ani bezpieczeństwie lasera na podstawie ogólnego poradnika.
- Zachować oryginalne blokady bezpieczeństwa; oprogramowanie nie może ich obchodzić. Zatrzymanie ruchu/energii musi działać także po awarii hosta.
- Nie podłączać przypadkowej płytki bez rozpoznania sygnałów i układów pośrednich. Nie traktować kopii flash jako gwarancji recovery.
- Oddzielić błędy mechaniki od problemów sieci. Stan „drukowanie przez most działa” jest pełnoprawnym wynikiem, nawet gdy wymiana płyty nie jest jeszcze wykonalna.

**Gate:** udokumentowany schemat i BOM własnego kontrolera, ograniczenia energetyczne, testy awarii, test dry-run mechaniki, następnie powtarzalne wydruki i ręczna akceptacja bezpieczeństwa. Żadna płyta nie trafia do klientów przed oceną wymaganych dla danego produktu uprawnień, badań i obowiązków.

## Etap 4 — produkt i usługowy biznes

Możliwe oferty, niezależne od kopiowania zamkniętego firmware lub projektów z zakazem komercyjnego użycia:

1. Instalacja utrzymywanego mostu druku i migracja urządzeń do IPP; cena obejmuje sprzęt, konfigurację i test danego modelu.
2. Diagnoza, naprawa mechaniki i dokumentowany test odzyskanego sprzętu.
3. Płatne utrzymanie hosta/adapterów, monitoring stanu bez treści dokumentów, wsparcie i szkolenie.
4. Własne zestawy kontrolera dla pojedynczych zweryfikowanych modeli, z dokumentacją, częściami i procedurą przywrócenia.

To propozycje modelu biznesowego, nie stwierdzenie, że wszystkie wymagania prawne lub produktowe już spełniono. Przed sprzedażą konkretnego zestawu trzeba ustalić prawa do wszystkich komponentów, obowiązki producenta zmodyfikowanego urządzenia i zakres odpowiedzialności za usługę.

## Pierwsze brakujące dane od właściciela urządzenia

Dokładna nazwa i kod produktu, firmware, system komputera, opis usterki, wynik własnej strony testowej, dostępne USB/Ethernet. Rewizję płyty dodaje się dopiero po bezpiecznej identyfikacji sprzętu przez odpowiednią osobę. Na tej podstawie wybierany jest pierwszy model; katalog popularności nie zastępuje egzemplarza laboratoryjnego.
