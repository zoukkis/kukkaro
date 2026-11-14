# catalog.csv: how the prices were set

- Hand-made list (101 products, 31 store-brand twins) with realistic Finnish supermarket prices for
  2026. Not copied from any store: no S-Group or other shop data was scraped or used.
- Coffee and chocolate were raised to reflect their sharp price rises in 2025 (Statistics Finland
  consumer price index: coffee over 25 % dearer than in 2024, chocolate also up sharply), see
  https://www.pty.fi/wp-content/uploads/2026/02/Analyysi_Elintarvikkeiden-myynnin-kehitys-Suomen-pt-kaupassa-2025.pdf
  and https://www.mtvuutiset.fi/artikkeli/suklaa-ja-kahvi-kallistuivat-viime-vuonna-rajusti/9282276
- Statistics Finland publishes price *changes* for food, not per-product average prices, so the
  other prices are hand-set. On 14 Nov the demo's key items were spot-checked by hand against
  typical online grocery shelf prices (milk, rye bread, eggs, energy drink, candy, cinnamon bun,
  chips, coffee) and our own numbers were adjusted where clearly off: energy drink 1.99, eggs 2.89
  (store brand 2.45), cinnamon bun 1.29, chips 2.95. Only our catalogue numbers changed; no shop's
  product list or data is stored in this repo.
- All receipts generated from this catalogue are synthetic and labelled as such.
