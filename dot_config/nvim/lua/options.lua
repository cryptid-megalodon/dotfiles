local o = vim.opt

o.number = true
o.hidden = true
o.scrolloff = 2
o.ignorecase = true
o.smartcase = true
o.expandtab = true
o.tabstop = 2
o.shiftwidth = 2
o.colorcolumn = "81"
o.termguicolors = true
o.showmode = true
o.clipboard = "unnamedplus"

-- Spelling errors: bold + undercurl instead of a background colour.
vim.api.nvim_create_autocmd("ColorScheme", {
  callback = function()
    vim.api.nvim_set_hl(0, "SpellBad", { bold = true, undercurl = true })
  end,
})
