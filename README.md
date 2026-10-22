# Canvas eklentisi

Canvas'ta açık projeleri yerel MCP bağlantısıyla Codex'e okutun. Eklenti açık projeleri, kartları, bağlantıları ve agent tanımlarını okuyabilir; projeleri değiştirmez veya üretim başlatmaz.

Windows'ta Canvas ve Codex aynı bilgisayarda çalışmalıdır. Eklenti `http://127.0.0.1:47321/mcp` adresine bağlanır. Canvas ayarlarındaki adres farklıysa, örneğin eski bir kurulumda `51098` görünüyorsa, [farklı adres kurulumu](docs/troubleshooting.md#canvas-adresi-farklı) için birkaç ek adım gerekir. Mevcut adresiniz otomatik değiştirilmez.

## Kurulum

1. Canvas'ı açın. **Ayarlar → MCP bağlantısı** bölümünde bağlantıyı açın.
2. Codex masaüstü uygulamasında **Eklentiler → Ekle → Pazar yeri ekle** yolunu izleyin.
3. Depo adresi olarak `https://github.com/kbingol/canvas-plugins` girin.
4. Eklenen **Canvas Plugins** kaynağında **Canvas → Yükle** seçin.
5. Aynı bilgisayarda çalışan **yeni bir Codex sohbeti** açın. Canvas açık kalsın.

Denemek için şunu yazın:

> Canvas bağlantısını kontrol et ve açık projelerimi listele.

Ardından bir projeyi adıyla belirterek kartlarını özetlemesini isteyin. Yalnızca bu bilgisayardaki açık Canvas projelerine erişilir. MCP sonuçlarının konuşmada kullanılması istemcinin veri işleme ayarlarına tabidir.

Terminalden kurulum isteyenler için:

```powershell
codex plugin marketplace add kbingol/canvas-plugins
codex plugin add canvas@canvas-plugins
```

Kurulumdan sonra yeni oturum başlatın. Bu depo, ekleyebileceğiniz bağımsız bir eklenti kataloğudur; OpenAI'nin resmî herkese açık dizininde listelendiği anlamına gelmez. [OpenAI'nin pazar yeri ve kurulum rehberi](https://developers.openai.com/plugins/build/plugins#add-a-marketplace-from-the-cli)

## Yardım

Bağlantı kurulamıyorsa [sorun giderme](docs/troubleshooting.md) sayfasına bakın. Paket yapısı ve doğrulama yaklaşımı [mimari notlarında](docs/architecture.md) bulunur. Lisans: [MIT](LICENSE).
