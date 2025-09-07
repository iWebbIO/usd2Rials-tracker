#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
from bs4 import BeautifulSoup
import csv
import os
from datetime import datetime
import re
import json
import subprocess
from pathlib import Path

class USD2RialsUpdater:
    def __init__(self, csv_file_path="USD2Rials.csv"):
        self.csv_file_path = csv_file_path
        self.url = "https://www.tgju.org/profile/price_dollar_rl/history"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
    
    def normalize_gregorian_date(self, date_str: str) -> str:

        if not date_str:
            return date_str
        date_str = date_str.strip()
        date_part = date_str.split()[0]
        date_part = date_part.replace('-', '/')
        parsed = None
        for fmt in ('%Y/%m/%d', '%m/%d/%Y', '%d/%m/%Y'):
            try:
                parsed = datetime.strptime(date_part, fmt)
                break
            except ValueError:
                continue
        if parsed is None:
            try:
                parts = re.split(r'[/-]', date_part)
                if len(parts) == 3:
                    if len(parts[0]) == 4 and parts[0].isdigit():
                        y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
                    elif len(parts[2]) == 4 and parts[2].isdigit():
                        d, m, y = int(parts[0]), int(parts[1]), int(parts[2])
                    else:
                        raise ValueError
                    parsed = datetime(y, m, d)
            except Exception:
                parsed = None
        if parsed:
            return f"{parsed.month}/{parsed.day}/{parsed.year}"
        return date_str

    def fetch_latest_price(self):
        """از وبسایت tgju آخرین قیمت دلار را دریافت می‌کند"""
        try:
            response = requests.get(self.url, headers=self.headers, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # پیدا کردن جدول تاریخچه قیمت
            table = soup.find('table', {'class': 'table widgets-dataTable table-hover text-center history-table'})
            if not table:
                raise ValueError("جدول قیمت در وبسایت پیدا نشد")
            
            # پیدا کردن اولین ردیف داده (بدون هدر)
            first_row = table.find('tbody').find('tr')
            if not first_row:
                raise ValueError("هیچ ردیف داده‌ای در جدول پیدا نشد")
            
            cells = first_row.find_all('td')
            if len(cells) < 8:
                raise ValueError("تعداد ستون‌های مورد انتظار در جدول پیدا نشد")
            
            # استخراج داده‌ها از ردیف اول
            # ترتیب: بیشترین، کمترین، بیشترین، میانگین، تغییر، درصد تغییر، تاریخ میلادی، تاریخ شمسی
            min_price_text = cells[1].get_text(strip=True)  # کمترین قیمت
            max_price_text = cells[2].get_text(strip=True)  # بیشترین قیمت
            raw_gregorian_date = cells[6].get_text(strip=True)  # تاریخ میلادی (خام از سایت)
            gregorian_date = self.normalize_gregorian_date(raw_gregorian_date)  # نرمال‌سازی به Month/Day/Year (M/D/YYYY)
            persian_date = cells[7].get_text(strip=True)    # تاریخ شمسی
            
            # تبدیل قیمت‌ها به عدد
            min_price = int(min_price_text.replace(',', ''))
            max_price = int(max_price_text.replace(',', ''))
            avg_price = (min_price + max_price) // 2
            
            return {
                'date_pr': persian_date,
                'date_gr': gregorian_date,
                'source': 'tgju',
                'price_avg': avg_price
            }
            
        except Exception as e:
            print(f"خطا در دریافت اطلاعات از وبسایت: {str(e)}")
            return None
    
    def get_last_entry(self):
        """آخرین ردیف از فایل CSV را بازمی‌گرداند"""
        try:
            if not os.path.exists(self.csv_file_path):
                return None
                
            with open(self.csv_file_path, 'r', encoding='utf-8') as file:
                csv_reader = csv.DictReader(file)
                last_row = None
                for row in csv_reader:
                    last_row = row
                return last_row
        except Exception as e:
            print(f"خطا در خواندن آخرین ردیف: {str(e)}")
            return None
    
    def is_new_data(self, new_data, last_entry):
        """بررسی می‌کند که آیا داده جدید است یا نه"""
        if not last_entry:
            return True
        return new_data['date_pr'] != last_entry['date_pr']
    
    def append_to_csv(self, new_data):
        """داده جدید را به فایل CSV اضافه می‌کند"""
        try:
            file_exists = os.path.exists(self.csv_file_path)
            
            with open(self.csv_file_path, 'a', newline='', encoding='utf-8') as file:
                fieldnames = ['date_pr', 'date_gr', 'source', 'price_avg']
                writer = csv.DictWriter(file, fieldnames=fieldnames)
                
                # اگر فایل وجود ندارد، هدر را بنویس
                if not file_exists:
                    writer.writeheader()
                
                writer.writerow(new_data)
            return True
        except Exception as e:
            print(f"خطا در نوشتن در فایل CSV: {str(e)}")
            return False
    
    def calculate_price_change(self, current_price, previous_price):
        """محاسبه تغییر قیمت و جهت آن"""
        if not previous_price:
            return 0, ""
        
        change = current_price - int(previous_price)
        if change > 0:
            return change, "↗️"
        elif change < 0:
            return change, "↘️"
        else:
            return 0, "➡️"

    # --- JSON helpers ---
    def to_iso_date(self, date_gr: str) -> str:
        """تبدیل تاریخ میلادی (M/D/YYYY و انواع مشابه) به ISO 8601 (YYYY-MM-DD)."""
        if not date_gr:
            return ""
        norm = self.normalize_gregorian_date(date_gr)
        try:
            dt = datetime.strptime(norm, "%m/%d/%Y")
            return dt.strftime("%Y-%m-%d")
        except Exception:
            try:
                parts = re.split(r"[/-]", norm)
                if len(parts) == 3:
                    m, d, y = int(parts[0]), int(parts[1]), int(parts[2])
                    return f"{y:04d}-{m:02d}-{d:02d}"
            except Exception:
                pass
        return ""

    def get_csv_row_count(self) -> int:
        """تعداد ردیف‌های CSV را برمی‌گرداند (بدون هدر)"""
        try:
            if not os.path.exists(self.csv_file_path):
                return 0
            with open(self.csv_file_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                next(reader, None)  # رد کردن هدر
                return sum(1 for _ in reader)
        except Exception as e:
            print(f"خطا در شمارش ردیف‌های CSV: {e}")
            return 0

    def regenerate_json_files(self, pretty_path: str = "USD2Rials.json", min_path: str = "USD2Rials.min.json") -> tuple[bool, int]:
        """از روی CSV دو خروجی JSON تولید می‌کند:
        1) فایل غیر فشرده شامل تمام ستون‌ها به صورت آرایه‌ای از آبجکت‌ها
        2) فایل مینیمال به صورت [["YYYY-MM-DD", price], ...]
        برمی‌گرداند: (موفقیت, تعداد ردیف‌ها)
        """
        try:
            full_rows = []
            min_rows = []
            row_count = 0
            with open(self.csv_file_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    row_count += 1
                    date_pr = (row.get('date_pr') or '').strip()
                    date_gr = (row.get('date_gr') or '').strip()
                    source = (row.get('source') or '').strip()
                    price_str = (row.get('price_avg') or '').replace(',', '').strip()
                    try:
                        price = int(price_str)
                    except Exception:
                        continue
                    # آرایه کامل
                    full_rows.append({
                        'date_pr': date_pr,
                        'date_gr': date_gr,
                        'source': source,
                        'price_avg': price
                    })
                    # آرایه مینیمال
                    iso = self.to_iso_date(date_gr)
                    if iso:
                        min_rows.append([iso, price])
            # مرتب‌سازی بر اساس تاریخ
            min_rows.sort(key=lambda x: x[0])
            full_rows.sort(key=lambda item: (self.to_iso_date(item.get('date_gr', '')) or '9999-99-99'))
            # نوشتن فایل‌ها
            with open(min_path, 'w', encoding='utf-8') as fmin:
                json.dump(min_rows, fmin, ensure_ascii=False, separators=(',', ':'))
            with open(pretty_path, 'w', encoding='utf-8') as fpretty:
                json.dump(full_rows, fpretty, ensure_ascii=False, indent=2)
            print("✅ فایل‌های JSON با موفقیت به‌روزرسانی شدند")
            return True, row_count
        except Exception as e:
            print(f"⚠️ خطا در به‌روزرسانی JSON: {e}")
            return False, 0
    
    def update_readme(self, latest_data, last_entry=None, csv_row_count=0):
        """فایل README را با آخرین اطلاعات به‌روزرسانی می‌کند (RTL + راست‌چین)"""
        try:
            # محاسبه تغییر قیمت
            current_price = latest_data['price_avg']
            previous_price = last_entry['price_avg'] if last_entry else None
            price_change, arrow = self.calculate_price_change(current_price, int(previous_price) if previous_price else None)
            
            # ایجاد محتوای HTML راست‌به‌چپ برای GitHub
            readme_content = f"""
<div dir="rtl" align="right">
  <h1>آرشیو قیمت دلار به ریال</h1>

  <h2>📊 آخرین اطلاعات</h2>
  <p><strong>آخرین به‌روزرسانی:</strong> {latest_data['date_pr']} | <strong>قیمت ثبت شده:</strong> {latest_data['price_avg']:,} ریال {arrow}</p>
"""
            
            if price_change != 0:
                readme_content += f"  <p><strong>تغییر نسبت به روز قبل:</strong> {price_change:+,} ریال</p>\n"
            
            # اضافه کردن تعداد ردیف‌های CSV
            readme_content += f"  <p><strong>تعداد ردیف‌:</strong> {csv_row_count:,}</p>\n"
            
            readme_content += """
  <hr />

  <h2>🔍 درباره مخزن</h2>
  <p>این مخزن حاوی اطلاعات تاریخچه قیمت دلار آمریکا به ریال ایران است که به صورت خودکار و روزانه از سایت <strong>tgju.org</strong> جمع‌آوری می‌شود.</p>
  <p>داده‌ها از تاریخ ۷ مهرماه ۱۳۶۰ تا به امروز هستند.</p>
  <p>داده‌های اولیه این مخزن از سایت <a href="https://d-learn.ir/usd-price/">مدرسه دقیقه</a> برداشته شده‌است و به صورت دوره‌ای این داده‌ در همین لینک بارگذاری می‌شود.</p>

  <h3>📋 توضیحات و فرایند:</h3>
  <ul>
    <li><strong>به‌روزرسانی خودکار</strong>: هر روز ساعت ۱۱:۰۰ صبح به وقت تهران</li>
    <li><strong>تاریخ دوگانه</strong>: شامل تاریخ شمسی و میلادی</li>
    <li><strong>قیمت میانگین</strong>: محاسبه شده از کمترین و بیشترین قیمت روز</li>
    <li><strong>نمایش تغییرات</strong>: مقایسه با روز قبل همراه با نشانگر در مخزن</li>
  </ul>

  <h3>📊 ساختار داده‌ها:</h3>
  <table>
    <thead>
      <tr><th>ستون</th><th>توضیح</th></tr>
    </thead>
    <tbody>
      <tr><td><code>date_pr</code></td><td>تاریخ شمسی (فارسی)</td></tr>
      <tr><td><code>date_gr</code></td><td>تاریخ میلادی (گریگورین)</td></tr>
      <tr><td><code>source</code></td><td>منبع اطلاعات (tgju)</td></tr>
      <tr><td><code>price_avg</code></td><td>میانگین قیمت روز (ریال)</td></tr>
    </tbody>
  </table>
</div>
"""
            
            with open('README.md', 'w', encoding='utf-8') as f:
                f.write(readme_content)
            
            return True
        except Exception as e:
            print(f"خطا در به‌روزرسانی README: {str(e)}")
            return False
    
    def is_first_day_of_persian_month(self, persian_date: str) -> bool:
        """بررسی می‌کند که آیا تاریخ شمسی روز اول ماه است یا نه"""
        try:
            # فرمت تاریخ شمسی معمولاً به صورت "۱۴۰۳/۰۶/۰۱" است
            parts = persian_date.replace('/', ' ').replace('-', ' ').split()
            if len(parts) >= 3:
                day = parts[2].strip()
                # تبدیل اعداد فارسی به انگلیسی
                persian_to_english = str.maketrans('۰۱۲۳۴۵۶۷۸۹', '0123456789')
                day_english = day.translate(persian_to_english)
                return day_english == '01' or day_english == '1'
            return False
        except Exception as e:
            print(f"خطا در بررسی روز اول ماه: {e}")
            return False
    
    def create_github_release(self, latest_data, csv_row_count: int) -> bool:
        """ایجاد GitHub Release با فایل‌های CSV و JSON"""
        try:
            github_token = os.getenv('GITHUB_TOKEN')
            if not github_token:
                print("⚠️ GITHUB_TOKEN تنظیم نشده است")
                return False
            
            # تولید نام تگ با فرمت تاریخ میلادی و شمسی
            gregorian_date = latest_data['date_gr']
            persian_date = latest_data['date_pr']
            
            # تبدیل تاریخ میلادی به فرمت YYYYMMDD
            try:
                dt = datetime.strptime(gregorian_date, "%m/%d/%Y")
                gregorian_formatted = dt.strftime("%Y%m%d")
            except:
                gregorian_formatted = gregorian_date.replace('/', '')
            
            # تبدیل تاریخ شمسی به فرمت YYYYMMDD
            persian_formatted = persian_date.replace('/', '').replace('-', '')
            
            tag_name = f"{gregorian_formatted}-{persian_formatted}"
            release_name = f"به‌روزرسانی {persian_date} - {gregorian_date}"
            
            release_body = f"""به‌روزرسانی شده تا {persian_date} - {gregorian_date}
تعداد ردیف: {csv_row_count:,}"""
            
            # ایجاد release با GitHub CLI
            cmd = [
                'gh', 'release', 'create', tag_name,
                '--title', release_name,
                '--notes', release_body,
                'USD2Rials.csv',
                'USD2Rials.json',
                'USD2Rials.min.json'
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
            
            if result.returncode == 0:
                print(f"✅ GitHub Release {tag_name} با موفقیت ایجاد شد")
                return True
            else:
                print(f"❌ خطا در ایجاد GitHub Release: {result.stderr}")
                return False
                
        except Exception as e:
            print(f"خطا در ایجاد GitHub Release: {e}")
            return False
    
    def send_telegram_message(self, latest_data, csv_row_count: int) -> bool:
        """ارسال پیام تلگرام با فایل‌های پروژه"""
        try:
            bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
            chat_id = os.getenv('TELEGRAM_CHAT_ID')
            
            if not bot_token or not chat_id:
                print("⚠️ TELEGRAM_BOT_TOKEN یا TELEGRAM_CHAT_ID تنظیم نشده است")
                return False
            
            message = f"""به‌روزرسانی تا {latest_data['date_pr']} - {latest_data['date_gr']}
تعداد ردیف‌های CSV: {csv_row_count:,}"""
            
            # ارسال پیام متنی
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            data = {
                'chat_id': chat_id,
                'text': message
            }
            
            response = requests.post(url, data=data)
            if response.status_code != 200:
                print(f"خطا در ارسال پیام تلگرام: {response.text}")
                return False
            
            # ارسال فایل CSV
            url_doc = f"https://api.telegram.org/bot{bot_token}/sendDocument"
            
            files_to_send = ['USD2Rials.csv', 'USD2Rials.json']
            
            for file_path in files_to_send:
                if os.path.exists(file_path):
                    with open(file_path, 'rb') as file:
                        files = {'document': file}
                        data = {'chat_id': chat_id}
                        response = requests.post(url_doc, data=data, files=files)
                        
                        if response.status_code == 200:
                            print(f"✅ فایل {file_path} با موفقیت ارسال شد")
                        else:
                            print(f"❌ خطا در ارسال فایل {file_path}: {response.text}")
                else:
                    print(f"⚠️ فایل {file_path} یافت نشد")
            
            return True
            
        except Exception as e:
            print(f"خطا در ارسال پیام تلگرام: {e}")
            return False
    
    def run(self):
        """اجرای فرآیند اصلی به‌روزرسانی"""
        print("🔄 شروع فرآیند به‌روزرسانی قیمت دلار...")
        
        # دریافت آخرین قیمت از وبسایت
        latest_data = self.fetch_latest_price()
        if not latest_data:
            print("❌ خطا در دریافت اطلاعات از وبسایت")
            return False
        
        print(f"📊 قیمت جدید دریافت شد: {latest_data['date_pr']} - {latest_data['price_avg']:,} ریال")
        
        # دریافت آخرین ردیف از فایل
        last_entry = self.get_last_entry()
        
        # بررسی جدید بودن داده
        is_new_data = self.is_new_data(latest_data, last_entry)
        
        if is_new_data:
            # اضافه کردن به CSV
            if self.append_to_csv(latest_data):
                print("✅ داده جدید با موفقیت به فایل CSV اضافه شد")
                
                # تولید/به‌روزرسانی JSON ها و دریافت تعداد ردیف‌ها
                json_success, csv_row_count = self.regenerate_json_files()
                
                # به‌روزرسانی README با تعداد ردیف‌ها
                if self.update_readme(latest_data, last_entry, csv_row_count):
                    print("✅ فایل README با موفقیت به‌روزرسانی شد")
                else:
                    print("⚠️ خطا در به‌روزرسانی README")
                
                # ایجاد GitHub Release برای داده‌های جدید
                self.create_github_release(latest_data, csv_row_count)
                
                # بررسی روز اول ماه شمسی برای ارسال تلگرام
                if self.is_first_day_of_persian_month(latest_data['date_pr']):
                    print("📅 روز اول ماه شمسی تشخیص داده شد - ارسال پیام تلگرام")
                    self.send_telegram_message(latest_data, csv_row_count)
                
                return True
            else:
                print("❌ خطا در اضافه کردن داده به فایل")
                return False
        else:
            print("ℹ️ داده جدیدی برای اضافه کردن وجود ندارد")
            # حتی اگر داده جدید نباشد، README و JSONها را به‌روزرسانی کن
            json_success, csv_row_count = self.regenerate_json_files()
            self.update_readme(latest_data, last_entry, csv_row_count)
            
            # بررسی روز اول ماه شمسی برای ارسال تلگرام (حتی اگر داده جدید نباشد)
            if self.is_first_day_of_persian_month(latest_data['date_pr']):
                print("📅 روز اول ماه شمسی تشخیص داده شد - ارسال پیام تلگرام")
                self.send_telegram_message(latest_data, csv_row_count)
            
            return True

if __name__ == "__main__":
    updater = USD2RialsUpdater()
    success = updater.run()
    exit(0 if success else 1)
