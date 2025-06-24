\version "2.24.4"
% automatically converted by musicxml2ly from C:\Users\momoka\Documents\workplace5\output(xml)\ホール・ニューワールド_Trumpet_in_B__1.xml
\pointAndClickOff

\header {
    title =  "Music21 Fragment"
    composer =  "Music21"
    encodingsoftware =  "music21 v.9.7.0"
    encodingdate =  "2025-06-12"
    }

#(set-global-staff-size 20.0)
\paper {
    
    }
\layout {
    \context { \Score
        skipBars = ##t
        autoBeaming = ##f
        }
    }
PartPddZeroSevenSevenFiveThreeSixeefOneNineZeroThreeZerobaThreecOneSixEightdNineZeroEightNineFourSevenTwobVoiceOne = 
\relative gis' {
    \clef "treble" \numericTimeSignature\time 4/4 \key as \major
    \transposition bes | % 1
    \tempo 4=120 gis4 bes8 c2 ~ c8 | % 2
    gis4 c8 cis4. bes4 | % 3
    gis4 bes8 c2 ~ c8 | % 4
    gis4 c8 cis4. bes4 | % 5
    R1 | % 6
    r4. es,8 \stemUp c'8 [ \stemUp es,8 ] \stemUp bes'8 [ \stemUp es,8 ]
    | % 7
    gis2 r2 | % 8
    r2. \stemUp g16 [ \stemUp gis16 \stemUp bes16 \stemUp c16 ] | % 9
    cis16 r2... | \barNumberCheck #10
    R1*2 | % 12
    r4. es,8 \stemUp c'8 [ \stemUp es,8 ] \stemUp bes'8 [ \stemUp es,8 ]
    | % 13
    gis2 r2 | % 14
    R1*2 | % 16
    f2 es2 | % 17
    bes'4 a8 c4 bes4 g8 | % 18
    bes4 gis4 g4 gis4 | % 19
    f8 g4 bes4 gis4 c8 ~ | \barNumberCheck #20
    c4. r2 r8 | % 21
    r4 \stemUp g8 [ \stemUp gis8 ] bes4 g4 | % 22
    c2 r2 | % 23
    R1 | % 24
    r2 \times 2/3 {
        c,4 cis4 es4 }
    | % 25
    g4 f4 es4. gis,8 | % 26
    g'4 gis8 es4. r8 gis8 | % 27
    c4 bes8 gis4 f4 gis8 ~ | % 28
    gis8 bes4 r2 r8 | % 29
    r4 \stemUp g8 [ \stemUp gis8 ] bes4 g4 | \barNumberCheck #30
    c2 r2 | % 31
    R1 | % 32
    r2 \times 2/3 {
        c,4 cis4 es4 }
    | % 33
    g4 f4 es4. gis,8 | % 34
    g'4 gis8 es4. r8 gis8 | % 35
    c4 bes4 gis4 bes4 | % 36
    cis4 c4 gis4 g4 | % 37
    gis2 r4. f8 ~ | % 38
    f8 es4 bes'4 gis4. | % 39
    \key f \major r8 a16 r16 c16 r8. bes16 r16 c16 r16 c16 r16 a16 r16 |
    \barNumberCheck #40
    r8 a16 r16 c16 r8. bes16 r16 c16 r16 c16 r16 a16 r16 | % 41
    r8 a16 r16 c16 r8. bes16 r16 c16 r16 c16 r16 a16 r16 | % 42
    d2 c4. r8 | % 43
    R1*3 | % 46
    r4. a8 bes4 d4 | % 47
    c1 ~ | % 48
    c4 r8 a8 bes4 d4 | % 49
    c4 g8 bes4 a4 a8 ~ | \barNumberCheck #50
    a4 r4 \times 2/3 {
        a4 bes4 c4 }
    | % 51
    e4 d4 c4. f,8 | % 52
    e'4 f8 c2 f,8 | % 53
    a4 g8 f4 d4 f8 ~ | % 54
    f8 g2 ~ g8 r4 | % 55
    r4 \stemDown c8 [ \stemDown c8 ] \times 2/3 {
        c4 bes4 a4 }
    | % 56
    f1 | % 57
    r4 \stemDown bes8 [ \stemDown bes8 ] \times 2/3 {
        bes4 a4 g4 }
    | % 58
    \times 2/3  {
        a4 f2 }
    \times 2/3  {
        a4 bes4 c4 }
    | % 59
    e4 d4 c4. f,8 | \barNumberCheck #60
    e'4 f8 c2 f,8 | % 61
    a4 g4 f4 g4 | % 62
    bes4 a4 f4 e4 | % 63
    f1 ~ | % 64
    f4 r2. | % 65
    r4. a8 bes4 d4 | % 66
    c1 | % 67
    r4. a8 bes4 d4 | % 68
    c4 r2. | % 69
    a4 g8 bes4 a8 f4 | \barNumberCheck #70
    c1 | % 71
    \tempo 4=120 a'4 g8 \tempo 4=105 bes4 \tempo 4=90 a8 f4 | % 72
    \tempo 4=60 c'1 \bar "|."
    }


% The score definition
\score {
    <<
        
        \new Staff
        <<
            \set Staff.instrumentName = "Trumpet in B♭ 1"
            \set Staff.shortInstrumentName = "Tpt"
            
            \context Staff << 
                \mergeDifferentlyDottedOn\mergeDifferentlyHeadedOn
                \context Voice = "PartPddZeroSevenSevenFiveThreeSixeefOneNineZeroThreeZerobaThreecOneSixEightdNineZeroEightNineFourSevenTwobVoiceOne" {  \PartPddZeroSevenSevenFiveThreeSixeefOneNineZeroThreeZerobaThreecOneSixEightdNineZeroEightNineFourSevenTwobVoiceOne }
                >>
            >>
        
        >>
    \layout {}
    % To create MIDI output, uncomment the following line:
    %  \midi {\tempo 4 = 120 }
    }

