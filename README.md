# Canvas eklentisi

Canvas'ta aÃ§Ä±k projeleri yerel MCP baÄŸlantÄ±sÄ±yla Codex'e okutun; kendi asistanÄ±nÄ±zÄ± oluÅŸturup `.flowast` paketi olarak dÄ±ÅŸarÄ± aktarÄ±n. Eklenti aÃ§Ä±k projeleri, kartlarÄ±, baÄŸlantÄ±larÄ± ve agent tanÄ±mlarÄ±nÄ± okuyabilir. Asistan oluÅŸturma ve dÄ±ÅŸarÄ± aktarma paket dosyalarÄ± yazar; projeleri deÄŸiÅŸtirmez veya asistan Ã§alÄ±ÅŸtÄ±rmaz.

Windows'ta Canvas ve Codex aynÄ± bilgisayarda Ã§alÄ±ÅŸmalÄ±dÄ±r. Canvas ve eklenti aynÄ± sabit yerel HTTP adresini kullanÄ±r: `http://127.0.0.1:47321/mcp`. KullanÄ±cÄ±nÄ±n adres veya config dosyasÄ± dÃ¼zenlemesi gerekmez.

**Gereksinim:** Bu sabit adresi kullanan gÃ¼ncel Canvas sÃ¼rÃ¼mÃ¼. Asistan oluÅŸturma iÃ§in uygulamanÄ±n `canvas_get_assistant`, `canvas_create_assistant` ve `canvas_export_assistant` araÃ§larÄ±nÄ± sunmasÄ± gerekir. Eklenti yÃ¼klemek Ã§alÄ±ÅŸan Canvas sÃ¼rÃ¼mÃ¼nÃ¼ gÃ¼ncellemez; uygulama gÃ¼ncellemesinden sonra yeni sÃ¼rÃ¼mÃ¼ aÃ§Ä±n.

## Kurulum

1. Canvas'Ä± aÃ§Ä±n. **Ayarlar â†’ MCP baÄŸlantÄ±sÄ±** bÃ¶lÃ¼mÃ¼nde baÄŸlantÄ±yÄ± aÃ§Ä±n.
2. Codex masaÃ¼stÃ¼ uygulamasÄ±nda **Eklentiler â†’ Ekle â†’ Pazar yeri ekle** yolunu izleyin.
3. Depo adresi olarak `https://github.com/kbingol/canvas-plugins` girin.
4. Eklenen **Canvas Plugins** kaynaÄŸÄ±nda **Canvas â†’ YÃ¼kle** seÃ§in.
5. AynÄ± bilgisayarda Ã§alÄ±ÅŸan **yeni bir Codex sohbeti** aÃ§Ä±n. Canvas aÃ§Ä±k kalsÄ±n.

Denemek iÃ§in ÅŸunu yazÄ±n:

> Canvas baÄŸlantÄ±sÄ±nÄ± kontrol et ve aÃ§Ä±k projelerimi listele.

ArdÄ±ndan bir projeyi adÄ±yla belirterek kartlarÄ±nÄ± Ã¶zetlemesini isteyin. YalnÄ±zca bu bilgisayardaki aÃ§Ä±k Canvas projelerine eriÅŸilir. MCP sonuÃ§larÄ±nÄ±n konuÅŸmada kullanÄ±lmasÄ± istemcinin veri iÅŸleme ayarlarÄ±na tabidir.

## Kendi asistanÄ±nÄ±zÄ± oluÅŸturun

Ã–rneÄŸin ÅŸunu isteyin:

> Canvas'ta metinleri TÃ¼rkÃ§eye Ã§eviren bir asistan oluÅŸtur ve .flowast olarak dÄ±ÅŸarÄ± aktar.

Codex, talimatlarÄ± ve gerekiyorsa skill'leri hazÄ±rlar; Canvas bunlarÄ± doÄŸrulayÄ±p `%LOCALAPPDATA%/Algomim/Canvas/assistants/<id>` klasÃ¶rÃ¼ne kaydeder. Yeni asistan uygulamada hemen gÃ¶rÃ¼nÃ¼r. DÄ±ÅŸarÄ± aktarÄ±lan `.flowast` dosyasÄ± varsayÄ±lan olarak Canvas'Ä±n yerel `Exports` klasÃ¶rÃ¼ne yazÄ±lÄ±r; sonucu dÃ¶nen dosya yolundan paylaÅŸabilirsiniz. AsistanÄ± kullanmak iÃ§in Canvas'ta Ã§alÄ±ÅŸtÄ±rÄ±n; MCP Ã¼zerinden paket oluÅŸturmak modeli veya gÃ¶rsel Ã¼retimini baÅŸlatmaz.

Mevcut bir asistanÄ±n tam tanÄ±mÄ± okunabilir ve yÃ¼klenmiÅŸ paketler dÄ±ÅŸarÄ± aktarÄ±labilir. OluÅŸturma mevcut paketin Ã¼zerine yazmaz; aynÄ± kimlikle gÃ¼ncelleme veya silme aracÄ± yoktur. `.flowast` dosyasÄ±nÄ± baÅŸka bir Canvas'ta **Ayarlar â†’ Asistanlar â†’ Asistan ekle** ile yÃ¼kleyebilirsiniz.

Terminalden kurulum isteyenler iÃ§in:

```powershell
codex plugin marketplace add kbingol/canvas-plugins
codex plugin add canvas@canvas-plugins
```

Kurulumdan sonra yeni oturum baÅŸlatÄ±n. Bu depo, ekleyebileceÄŸiniz baÄŸÄ±msÄ±z bir eklenti kataloÄŸudur; OpenAI'nin resmÃ® herkese aÃ§Ä±k dizininde listelendiÄŸi anlamÄ±na gelmez. [OpenAI'nin pazar yeri ve kurulum rehberi](https://developers.openai.com/plugins/build/plugins#add-a-marketplace-from-the-cli)

## YardÄ±m

BaÄŸlantÄ± kurulamÄ±yorsa [sorun giderme](docs/troubleshooting.md) sayfasÄ±na bakÄ±n. Paket yapÄ±sÄ± ve doÄŸrulama yaklaÅŸÄ±mÄ± [mimari notlarÄ±nda](docs/architecture.md) bulunur. Lisans: [MIT](LICENSE).
