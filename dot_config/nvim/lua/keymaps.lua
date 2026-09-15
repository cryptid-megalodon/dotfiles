local map = vim.keymap.set

-- Turn off arrow keys in all modes; use h/j/k/l.
for _, key in ipairs({ "<Up>", "<Down>", "<Left>", "<Right>", "<Del>" }) do
  map({ "n", "v", "o", "i" }, key, "<Nop>")
end

-- Clear search highlight.
map("n", "<leader>h", "<cmd>nohlsearch<CR>", { desc = "Clear search highlight" })
