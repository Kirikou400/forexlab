@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\activate.bat (
  echo Please double-click setup.bat first.
  pause
  exit /b 1
)
call .venv\Scripts\activate.bat

:menu
cls
echo ====================================================
echo           ForexLab Research Terminal
echo ====================================================
echo  1. Save my Twelve Data API key
echo  2. Open the browser dashboard ^& backtester
echo  3. Load sample demo candles (instant test, no key)
echo  4. Download historical market data (Twelve Data)
echo  5. Check stored data quality
echo  6. Run a standard backtest (EUR/USD, 1h, train, EMA)
echo  7. Run a custom backtest (any pair, timeframe, strategy)
echo  8. Quit
echo.
set choice=
set /p choice=Type a number and press Enter:
if "%choice%"=="1" goto key
if "%choice%"=="2" goto dashboard
if "%choice%"=="3" goto demo
if "%choice%"=="4" goto fetch
if "%choice%"=="5" goto check
if "%choice%"=="6" goto std
if "%choice%"=="7" goto custom
if "%choice%"=="8" exit /b 0
goto menu

:key
echo.
echo Get a free key at https://twelvedata.com (sign up, then copy the API key).
set k=
set /p k=Paste your key here and press Enter:
> .env echo TWELVEDATA_API_KEY=%k%
echo Saved to .env.
pause
goto menu

:dashboard
echo Starting ForexLab server on http://127.0.0.1:8000 ...
start "ForexLab Dashboard" http://127.0.0.1:8000
python -m forexlab.web
pause
goto menu

:demo
echo Generating sample market data for EUR/USD, GBP/USD, USD/JPY, AUD/USD...
python -m forexlab.demo_data
pause
goto menu

:fetch
python -m forexlab.fetch_data
pause
goto menu

:check
python -m forexlab.check_data
pause
goto menu

:std
python -m forexlab.run_backtest --symbol EUR/USD --timeframe 1h --strategy ema_cross --split train --walkforward 3
pause
goto menu

:custom
set sym=EUR/USD
set tf=1h
set strat=ema_cross
set spl=train
echo Press Enter to keep the value shown in [brackets].
set /p sym=Pair: EUR/USD, GBP/USD, USD/JPY or AUD/USD [%sym%]:
set /p tf=Timeframe: 15min, 1h or 4h [%tf%]:
set /p strat=Strategy: ema_cross, sma_cross, macd_cross, rsi_reversal, donchian [%strat%]:
set /p spl=Data split: train, validation, or test [%spl%]:
python -m forexlab.run_backtest --symbol %sym% --timeframe %tf% --strategy %strat% --split %spl% --walkforward 3
pause
goto menu
