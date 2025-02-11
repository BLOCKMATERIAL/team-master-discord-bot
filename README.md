# 📘 Інструкція користувача для бота управління командою TeamMaster(5-slots)

Вітаємо! Цей бот допоможе вам створювати та керувати командами для гри Valorant у вашому Discord-сервері.

## 🛠️ Доступні команди:

### 1️⃣ Створення команди
**Команда:** `!create`
**Опис:** Створює нову команду з унікальним ID.
**Результат:** Бот створить нову команду, призначить вас лідером і надішле повідомлення з деталями команди, тегнувши @everyone.

### 2️⃣ Приєднання до команди
**Команда:** `!join [team_id]`
**Опис:** Дозволяє приєднатися до існуючої команди.
**Приклад:** `!join 12345`

### 3️⃣ Видалення гравця з команди (тільки для лідера)
**Команда:** `!remove [team_id] [player_name]`
**Опис:** Дозволяє лідеру команди видалити гравця.
**Приклад:** `!remove 12345 Гравець1`

### 4️⃣ Очищення складу команди (тільки для лідера)
**Команда:** `!clear [team_id]`
**Опис:** Очищає склад команди, залишаючи тільки лідера.
**Приклад:** `!clear 12345`

### 5️⃣ Перегляд складу команди або списку всіх команд
**Команда:** `!show [team_id]` або просто `!show`
**Опис:** Показує поточний склад вказаної команди або список всіх активних команд, якщо ID не вказано.
**Приклад:** `!show 12345` або `!show`

### 6️⃣ Розпуск команди (тільки для лідера)
**Команда:** `!disband [team_id]`
**Опис:** Розпускає вказану команду.
**Приклад:** `!disband 12345`

## 📝 Примітки:
- Кожна команда може мати максимум 5 гравців.
- Тільки лідер команди може видаляти гравців, очищати склад або розпускати команду.
- При спробі приєднатися до повної команди ви отримаєте повідомлення про помилку.
- Використовуйте ID команди для всіх операцій з нею.
- Час створення команди тепер відображається в інформації про команду.
- При відображенні складу команди, біля кожного гравця в дужках вказуються його ролі на сервері.

Насолоджуйтесь грою та командною роботою! 🎮🏆