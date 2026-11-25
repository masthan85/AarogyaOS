// https://docs.expo.dev/guides/using-eslint/
const { defineConfig } = require('eslint/config');
const expoConfig = require('eslint-config-expo/flat');

module.exports = defineConfig([
  expoConfig,
  {
    ignores: ['dist/*', '.expo/*'],
  },
  {
    rules: {
      // Apostrophes and quotes in <Text> render literally in React Native; escaping adds nothing.
      'react/no-unescaped-entities': 'off',
    },
  },
  {
    // Tests call jest.mock before importing, and group imports beside the cases that use them.
    files: ['**/__tests__/**'],
    rules: {
      'import/first': 'off',
      'import/no-duplicates': 'off',
      // jest.mock factories run before imports, so they must load modules with require().
      '@typescript-eslint/no-require-imports': 'off',
    },
  },
]);
