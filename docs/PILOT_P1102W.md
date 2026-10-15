# Pierwszy pilot: HP LaserJet Pro P1102w

**Status: kandydat wybrany do pilota; sprzęt fizycznie niezweryfikowany.** Profil nie oznacza `print-tested`, obsługi każdego wariantu ani gotowości do flashowania. Wybór opiera się na udokumentowanym USB i istniejących ścieżkach sterowników. Nie ma tu danych o liczbie sprzedanych lub nadal używanych egzemplarzy.

## Potwierdzone źródłami

| Ustalenie | Dowód i ograniczenie |
| --- | --- |
| Monochromatyczna drukarka laserowa, druk host-based, USB 2.0 i Wi-Fi 802.11b/g. | [Oficjalna karta HP](https://www.hp.com/us-en/shop/pdp/hp-laserjet-pro-p1102w-printer), sekcje Technical Specs / Ports / Print languages. Parametry wariantu i kod produktu należy porównać z egzemplarzem. |
| HP wymienia IPP i AirPrint w możliwościach sieciowych. | Ta sama karta HP; to nie dowód zgodności IPP Everywhere ani działania driverless na każdym firmware. Pilot nie zakłada natywnego IPP-over-USB. |
| Ścieżka HPLIP wymaga zamkniętej wtyczki. | [HP — HPLIP Binary Plug-In](https://developers.hp.com/hp-linux-imaging-and-printing/binary_plugin.html), wiersze P1102w oznaczone `Required` dla drukowania. To zależność tej ścieżki, nie dowód niemożliwości użycia innego sterownika. |
| Istnieje alternatywny sterownik foo2zjs z profilem dokładnie P1102w. | [Repozytorium OpenPrinting/foo2zjs](https://github.com/OpenPrinting/foo2zjs), [PPD P1102w](https://raw.githubusercontent.com/OpenPrinting/foo2zjs/main-fixes/PPD/HP-LaserJet_Pro_P1102w.ppd): model i filtr `foo2zjs-z2`. Obecność PPD nie dowodzi działania na naszym egzemplarzu. |

Tabela HP zawiera dwa historyczne zapisy nazwy P1102w z różnymi minimalnymi wersjami wtyczki. Nie używać tych minimów jako zalecenia instalacji starej wersji: wersję zgodnego HPLIP i wtyczki trzeba ustalić dla utrzymywanego systemu hosta. Wtyczka ma osobną licencję; toolkit nie dołącza jej ani cudzych obrazów firmware.

## Cel pilota: USB → host Linux → klienci IPP

Drukarka łączy się **przez USB** z hostem Linux, np. Raspberry Pi lub małym komputerem. Host renderuje dokumenty i udostępnia kolejkę przez IPP; fabryczna elektronika drukarki pozostaje na miejscu. Klientem może być dowolny system z odpowiednią obsługą IPP, docelowo Windows, macOS, Linux, iOS i Android. Zgodność każdego obiecanego klienta wymaga osobnego fizycznego wydruku; nie deklarować jej po samym wykryciu kolejki.

USB jest pierwszą ścieżką, aby oddzielić problemy sterownika i mechaniki od Wi-Fi drukarki. Pilot nie wymaga wymiany jej płyty ani zmiany firmware. Utworzenie lokalnej kolejki driverless w obecnym toolkit nie zastępuje instalacji i konfiguracji takiego mostu USB.

| Ścieżka do porównania | Co sprawdzić na urządzeniu |
| --- | --- |
| HPLIP + właściwa wtyczka HP | Dostępność wersji dla wybranego Linux/architektury, zgodność licencji i wersji, pełny wydruk oraz zachowanie po zimnym starcie. To otwarty host z zamkniętą zależnością. |
| foo2zjs / profil `foo2zjs-z2` | Właściwy pakiet i PPD, działanie filtrów, jakość i restarty. Ustalić ewentualne dodatkowe zależności lub ładowanie binarnych danych; sam otwarty filtr nie dowodzi całkowicie otwartego toru. To sterownik hosta, nie zamiennik firmware drukarki. |

Obie ścieżki pozostają **do przetestowania**. Nie kopiować historycznych skryptów pobierających z przypadkowych adresów i nie uruchamiać automatycznej instalacji bez przeglądu źródła. W raporcie zapisać wersje pakietów, pochodzenie oraz skróty użytych artefaktów. Następnie wybrać jeden działający wariant jako bazę pilota.

## Zamrożony gate fizyczny

Zgodnie z [roadmapą sprzętową](HARDWARE_ROADMAP.md), status `print-tested` wymaga łącznie:

1. Identyfikacji modelu, SKU/wariantu, zgłoszonego firmware i dostępnej rewizji oraz hosta/architektury, wersji sterownika i zależności. Dane nieznane zapisać jawnie.
2. **10 kolejnych reprezentatywnych zadań druku** na tym egzemplarzu, z kontrolą tekstu, PDF, grafiki i zadania wielostronicowego. Człowiek potwierdza kompletność i czytelność wydruków.
3. Anulowania zadania i wznowienia pracy kolejki bez zawieszenia urządzenia ani hosta.
4. **3 cykli restartu** hosta i drukarki, z ponownym wykryciem i udanym wydrukiem po każdym cyklu. Odnotować ewentualne ponowne ładowanie danych wymaganych przez sterownik.
5. Raportu wersji, transportu, testowanych klientów i wyników; logi nie mogą ujawniać treści prywatnych dokumentów. Własne pliki testowe mają mieć niepoufne dane.

Testy tego profilu **nie zostały wykonane**. Profil nie zatwierdza aktualizacji, downgrade'u, jailbreaku ani recovery. Włączenie przyszłego zapisu wymaga osobnego gate z [MODEL_ADAPTERS.md](MODEL_ADAPTERS.md), z dokładnym dopasowaniem rewizji/firmware i wykonanym odzyskaniem urządzenia.

## Dane potrzebne do pierwszej sesji

- Fizyczny P1102w, sprawny przewód USB, papier i toner; wynik własnej strony testowej drukarki oraz opis usterki.
- Zdjęcie tabliczki lub odczyt modelu/SKU; numer seryjny zanonimizowany w publicznych materiałach. Bez otwierania urządzenia do samego pilota USB.
- Aktualny firmware, jeśli da się go bezpiecznie odczytać, oraz wybrany host Linux. Braku danych nie uzupełniać zgadywaniem.
- Lista rzeczywiście dostępnych systemów klientów; pierwszy pozytywny wynik dotyczy wyłącznie przetestowanych kombinacji.

## Granica zebranego materiału

[Strona sterowników HP dla modelu 4110306](https://support.hp.com/us-en/drivers/hp-laserjet-pro-p1102-printer-series/model/4110306) nie zwróciła treści podczas odczytu badawczego. Nie ustalono więc stamtąd aktualnej wersji firmware, dostępności instalatora ani zaleceń aktualizacji. Oficjalną kartę produktu i tabelę wtyczek HP odczytano; PPD OpenPrinting potwierdza istnienie konkretnej ścieżki sterownika. Żadne z tych źródeł nie zastępuje testu sprzętu.
