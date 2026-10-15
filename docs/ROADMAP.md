# Roadmapa HP regen toolkit

## v0.1 — działający warsztat lokalny

Panel + CLI, mDNS/IPP, ograniczony skan wskazanej sieci, diagnoza, raport, lokalna kolejka CUPS po zatwierdzeniu, offline preflight i logo. Bramka: testy offline, przegląd niezależny, rzeczywiste sprawdzenie interfejsu. Osobno oznaczamy brak fizycznej walidacji drukarki i platform innych niż bieżący host.

## v0.2 — pierwsza uratowana drukarka

Wybór dokładnego modelu i opisu awarii. Udokumentowany wydruk testowy, jakość, restart, utrata/odzyskanie połączenia. Profil zgodności powinien rozróżniać USB/Ethernet/Wi-Fi, skaner, duplex i zależność od zamkniętej wtyczki. Dodanie opakowanego mostu Linux/OpenPrinting oraz instalatora desktopowego; Windows dostaje natywny adapter kolejki zamiast poleceń CUPS.

## v0.3 — modelowe naprawy i aktualizacje

Import ustawień, legalne źródła firmware, weryfikacja zaufanego podpisu/manifestu, dokładna rewizja sprzętu i bootloadera, sprawdzony recovery, fizyczny test zapisu. Aktualizacja i downgrade są osobnymi możliwościami profilu, nigdy efektem znalezienia podobnej nazwy modelu. Obniżenie wersji może ponownie wprowadzać podatności; raport musi opisywać ten kompromis.

## Hardware — osobny tor rozwoju

Odwracalny most → pojedynczy mechanizm laboratoryjny → Linux host + MCU → własna płyta konkretnego modelu. Środowisko laboratoryjne, oryginalne interlocki i testy awarii poprzedzają sprzedaż zestawów. Nie powstaje obietnica „Arduino działa zamiast każdej płyty HP”. Szczegóły w [HARDWARE_ROADMAP.md](HARDWARE_ROADMAP.md).

## Dodatkowe narzędzia do scyzoryka

- Test jakości i kalibracji: dysze, pasy, kolory, duplex, wyrównanie i automatyczne porównanie skanu wydruku z wzorcem.
- Diagnoza sieci: opóźnienia, zerwane połączenia, izolacja Wi-Fi, VLAN/mDNS i poradnik kabla/mostu USB.
- Kopia konfiguracji, migracja kolejki i odwracanie własnych zmian.
- Paszport urządzenia: model/revizja/firmware, wykonane naprawy, części, testy, otwarte/zamknięte zależności.
- eSCL/SANE: odzyskiwanie skanera w urządzeniach wielofunkcyjnych.
- Katalog błędów i instrukcje serwisowe ze źródłem, jakością dowodu i warunkami zastosowania.
- Licznik odzyskanych urządzeń i kosztów napraw; ekologiczne szacunki dopiero z jawną metodologią.
- Audyt konfiguracji bezpieczeństwa: ekspozycja usług, domyślne ustawienia i dostępność poprawki, bez zbierania treści dokumentów.
- Zarządzanie częściami i kartridżami: zgodność, regeneracja, dostępność i naprawialność bez obietnicy obejścia każdego DRM.
- Laboratorium adapterów: symulator IPP, zapis oczyszczonych pakietów testowych, podpisane wydania i powtarzalne testy recovery.
