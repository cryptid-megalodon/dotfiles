-- Neovim config — plugins are managed by lazy.nvim (lua/plugins/*.lua) and
-- bootstrap themselves on first launch.

-- Leader must be set before lazy.nvim loads.
vim.g.mapleader = "v"
vim.g.maplocalleader = "v"

require("options")
require("keymaps")

-- Bootstrap lazy.nvim.
local lazypath = vim.fn.stdpath("data") .. "/lazy/lazy.nvim"
if not (vim.uv or vim.loop).fs_stat(lazypath) then
  vim.fn.system({
    "git", "clone", "--filter=blob:none", "--branch=stable",
    "https://github.com/folke/lazy.nvim.git", lazypath,
  })
end
vim.opt.rtp:prepend(lazypath)

require("lazy").setup("plugins", {
  change_detection = { notify = false },
})
