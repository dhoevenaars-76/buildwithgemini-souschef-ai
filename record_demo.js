const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

(async () => {
  const videoDir = path.join(__dirname, 'demo_video');
  if (!fs.existsSync(videoDir)) {
    fs.mkdirSync(videoDir, { recursive: true });
  }

  console.log("Launching headless browser...");
  const browser = await chromium.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });

  const context = await browser.newContext({
    viewport: { width: 1280, height: 720 },
    recordVideo: {
      dir: videoDir,
      size: { width: 1280, height: 720 }
    }
  });

  const page = await context.newPage();

  console.log("Navigating to SousChef AI frontend...");
  await page.goto('https://souschef-ai-frontend-572744788273.us-east1.run.app', { waitUntil: 'networkidle' });
  await page.waitForTimeout(2500);

  // 1. First prompt: Main culinary capability
  console.log("Sending Prompt 1: Recipe Search...");
  await page.fill('#input', 'Find a classic Italian pasta recipe and give me cooking instructions');
  await page.waitForTimeout(1000);
  await page.click('button.send-btn');

  console.log("Waiting for Agent response 1...");
  await page.waitForFunction(() => {
    const msgs = document.querySelectorAll('.msg.agent');
    return msgs.length >= 1 && !document.querySelector('.thinking');
  }, { timeout: 90000 });

  await page.waitForTimeout(4000);

  // 2. Second prompt: Richer prompt showing tool call & image generation
  console.log("Sending Prompt 2: Tool call & Image Generation...");
  await page.fill('#input', 'Generate a photo of Creamy Garlic Alfredo Pasta');
  await page.waitForTimeout(1000);
  await page.click('button.send-btn');

  console.log("Waiting for Agent response 2...");
  await page.waitForFunction(() => {
    const msgs = document.querySelectorAll('.msg.agent');
    return msgs.length >= 2 && !document.querySelector('.thinking');
  }, { timeout: 120000 });

  await page.waitForTimeout(5000);

  // Showcase Lightbox modal if image exists
  const img = await page.$('.a2img, img.a2img');
  if (img) {
    console.log("Clicking generated image to showcase Lightbox Modal...");
    await img.click();
    await page.waitForTimeout(3000);
    console.log("Closing Lightbox Modal...");
    await page.click('#lightbox');
    await page.waitForTimeout(2000);
  }

  // Showcase Dark Mode toggle
  console.log("Toggling Kitchen Dark Mode...");
  await page.click('#theme-toggle');
  await page.waitForTimeout(3500);

  console.log("Closing browser and saving video...");
  await context.close();
  await browser.close();

  const files = fs.readdirSync(videoDir);
  console.log("Recorded video files in directory:", files);
  if (files.length > 0) {
    const recordedFile = path.join(videoDir, files[0]);
    const targetPath = path.join(__dirname, 'souschef_ai_demo.webm');
    fs.copyFileSync(recordedFile, targetPath);
    console.log("Demo video successfully saved to:", targetPath);
  }
})();
