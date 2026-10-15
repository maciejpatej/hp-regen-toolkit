# Kontrakt adapterów modelowych i gate wydania

**Status v0.1:** brak włączonych adapterów zapisu firmware, jailbreaku lub sterowania mechaniką. Inspekcja IPP i offline preflight są działającymi funkcjami; ten dokument definiuje wymagania przyszłych rozszerzeń. Manifest dostarczony przez użytkownika pozostaje niezaufany.

## Poziomy wsparcia

| Poziom | Co wolno deklarować | Wymagane potwierdzenie |
| --- | --- | --- |
| `discovered` | W sieci odpowiada usługa IPP/IPPS. | Ograniczony odczyt protokołu, źródło i czas obserwacji. Nie jest to dowód zgodności firmware. |
| `identified` | Zebrano zgłaszaną przez urządzenie tożsamość i możliwości. | Rzeczywiste dane oraz jawne pola nieznane; dane z drukarki mogą być fałszywe. |
| `print-tested` | Konkretna kombinacja drukarka/host/sterownik drukuje. | Fizyczne wydruki, wersje i raport testu człowieka. |
| `repair-tested` | Określona naprawa ma sprawdzoną procedurę powrotu. | Egzemplarz laboratoryjny, dokładna tożsamość, powtarzalny wynik i wykonany recovery. |
| `write-enabled` | Można uruchomić wyłącznie nazwane, zatwierdzone operacje zapisu. | Wszystkie poniższe gates, przegląd kodu i jawne zatwierdzenie danej operacji przez właściciela. |

Nie przenosić poziomu wsparcia między rewizjami ani firmware. Seria handlowa lub zbliżona nazwa modelu nie wystarcza.

## Minimalny wpis adaptera

To projekt schematu; nie jest formatem obecnego endpointu preflight. Każdy przyszły adapter musi zawierać:

- `adapter_id`, wersję schematu, wersję adaptera i niezmienny identyfikator wydania kodu.
- Producenta, **dokładny model, kod produktu/SKU, rewizję sprzętu/płyty**, ewentualny wariant regionalny oraz listę jawnie obsługiwanych wersji firmware i bootloadera. Brak lub nieznana wersja blokuje zapis.
- Wymagany transport i identyfikatory sprzętu. VID/PID, IP i model z IPP są dowodami pomocniczymi, nie samodzielnym uprawnieniem do zapisu.
- Oddzielną listę operacji tylko do odczytu i operacji zapisu; skutki, wymaganą obecność fizyczną, uprawnienia i ograniczenia każdej z nich.
- Pochodzenie obrazu: oficjalny lub autoryzowany adres źródła, autor/wydawca, licencja, dozwolony sposób pobrania, dokładny rozmiar, **SHA-256**, format i zgodna tożsamość docelowa. Jeśli jest podpis, również zaufane pochodzenie klucza i wynik weryfikacji podpisu.
- Opis metody kopii i recovery, zakres danych kopii, warunki wstępne, wymagany sprzęt, wykonany raport odzyskania oraz jego ograniczenia.
- Fizyczny raport testów z datą, wersjami, identyfikatorem egzemplarza zanonimizowanym w publicznym raporcie, dowodami wydruków i osobą zatwierdzającą.
- Jawne nieobsługiwane warianty i znane usterki. Pole `unknown` nie może znaczyć `compatible`.

Hash sprawdza zgodność bajtów z deklaracją. **Hash nie uwierzytelnia deklaracji ani producenta.** Podpis bez zaufanego pochodzenia klucza również nie daje wystarczającego dowodu. Test preflight nie jest testem recovery.

## Plan wykonywania operacji

1. Użytkownik wybiera jedno urządzenie i potwierdza, że jest jego właścicielem lub administratorem uprawnionym do operacji.
2. Odczyt tożsamości i porównanie z dokładną listą adaptera. **Stop przy niezgodności, braku pola lub niejednoznaczności.** Nie zgadywać na podstawie nazwy.
3. Weryfikacja niezmiennego wydania adaptera oraz obrazu, jego pochodzenia i uprawnień do użycia. Odmówić dowolnej podmiany artefaktu po utworzeniu planu.
4. Kopia wspieranych danych, kontrola warunków recovery, zasilania i wymaganej obecności fizycznej. Sprawdzenie kopii nie może sugerować, że można przywrócić elementy nieobjęte kopią.
5. Podgląd planu: urządzenie, operacja, wersja przed/po, skrót obrazu, ryzyko i kroki odzyskania. Osobne zatwierdzenie fizycznej operacji przez człowieka.
6. Bezpośrednio przed zapisem ponowny odczyt tożsamości, ponowny hash tych samych bajtów oraz sprawdzenie blokady równoległych operacji. Zmiana danych zatrzymuje plan.
7. Jedna operacja na jednym urządzeniu; ograniczony czas, brak automatycznego ponowienia zapisu po timeout. Niepewny wynik trafia do diagnostyki/recovery, nie jest raportowany jako sukces.
8. Po operacji: odczyt wersji, uruchomienie urządzenia i fizyczny test funkcji. Sukces sieciowego requestu nie dowodzi sprawnego urządzenia.

Adres IP może zostać przejęty lub zmienić właściciela. Odczyt IPP może być podszyty. Adapter zapisu musi wykazać silniejszą metodę identyfikacji, np. zatwierdzone powiązanie z fizycznie podłączonym egzemplarzem. Bez tego zapis pozostaje zablokowany.

## Release gate dla zapisu

- Przegląd adaptera przez niezależnego weryfikatora; próba obalenia założeń o tożsamości, artefakcie i recovery.
- Testy: zły model/rewizja/firmware, nieznana wersja, podmieniony obraz, zmieniony manifest, przerwany odczyt, błędny podpis, utrata łącza, równoległe operacje. Oczekiwany wynik: bezpieczne zatrzymanie, nigdy „spróbuj mimo to”.
- **Recovery wykonany na realnym urządzeniu laboratoryjnym**, nie tylko opisany w README. Scenariusze utraty zasilania testuje kompetentny człowiek z odpowiednim zabezpieczeniem stanowiska.
- Raport ręcznego testu drukowania i wszystkich obiecanych funkcji, w tym skanowania, jeśli objęte wsparciem.
- Model i rewizja widoczne w publicznej macierzy zgodności; zastrzeżenia zapisane przed publikacją. Usunięcie niesprawdzonego wariantu nie wpływa na wsparcie przetestowanego.
- Do repo nie trafia cudzy zamknięty firmware ani wtyczka bez udokumentowanego uprawnienia do dystrybucji. Pobranie z cudzej strony nie oznacza prawa do redystrybucji.
- Dla metod odblokowania: osobny przegląd zakresu bezpieczeństwa i uprawnień. Dokument nie zawiera exploit payloadów, obchodzenia uwierzytelnienia ani instrukcji niszczenia zabezpieczeń. Taki adapter nie wynika automatycznie z samego życzenia „jailbreak”.

## Rozsądny pierwszy adapter

Najpierw adapter **tylko do odczytu i doboru otwartego sterownika** dla urządzenia fizycznie dostępnego zespołowi. Następnie most USB i test drukowania. Pierwszy adapter zapisu wymaga dodatkowo dokładnego modelu/SKU, rewizji, firmware, autoryzowanego obrazu i wykonalnego recovery. Do uzyskania tych danych żadna rodzina HP/Xerox nie otrzymuje zbiorczej deklaracji zgodności.

Kontekst ograniczeń integracji: [HPLIP — binarna wtyczka i osobna licencja](https://developers.hp.com/hp-linux-imaging-and-printing/binary_plugin.html), [OpenPrinting — przejście do Printer Applications](https://openprinting.github.io/cups/drivers.html). To źródła o obsłudze druku, nie certyfikaty bezpieczeństwa flashowania.
